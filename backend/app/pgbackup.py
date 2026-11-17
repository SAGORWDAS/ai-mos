"""Consistent PostgreSQL backup and verified restore into a different, empty database."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import asyncpg


def connection_args(url):
    parsed = urlsplit(url.replace("postgresql+asyncpg://", "postgresql://"))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("Explicit PostgreSQL database URL required")
    host = "[" + parsed.hostname + "]" if ":" in parsed.hostname else parsed.hostname
    authority = (
        (quote(unquote(parsed.username), safe="") + "@" if parsed.username else "")
        + host
        + (":" + str(parsed.port) if parsed.port else "")
    )
    safe = urlunsplit(("postgresql", authority, parsed.path, parsed.query, ""))
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "HOME",
            "APPDATA",
            "PGSSLMODE",
            "PGSSLROOTCERT",
            "PGSSLCERT",
            "PGSSLKEY",
        }
    }
    env["PGPASSWORD"] = unquote(parsed.password or "")
    env["PGCONNECT_TIMEOUT"] = "15"
    return safe, env


def executable(name, bin_dir=None):
    candidate = (
        Path(bin_dir) / (name + (".exe" if os.name == "nt" else ""))
        if bin_dir
        else shutil.which(name)
    )
    if not candidate or not Path(candidate).is_file():
        raise ValueError("Install matching PostgreSQL client tools or provide --bin-dir")
    return str(candidate)


async def inventory(connection):
    tables = await connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    counts = {}
    for row in tables:
        name = row["tablename"]
        counts[name] = await connection.fetchval(
            'SELECT count(*) FROM "' + name.replace('"', '""') + '"'
        )
    audit = hashlib.sha256()
    if "audit_logs" in counts:
        async for row in connection.cursor("SELECT * FROM audit_logs ORDER BY id"):
            audit.update(json.dumps(dict(row), sort_keys=True, default=str).encode())
    return {"counts": counts, "audit_sha256": audit.hexdigest()}


async def require_backup_role(connection):
    if not await connection.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
    ):
        raise ValueError("Use a dedicated backup administrator that can read every tenant")


async def backup(url, destination, bin_dir=None):
    destination = await asyncio.to_thread(Path(destination).resolve)
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    if destination.exists() or manifest_path.exists():
        raise FileExistsError("Choose a new backup path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe, env = connection_args(url)
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    temporary = None
    try:
        await require_backup_role(connection)
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            snapshot = await connection.fetchval("SELECT pg_export_snapshot()")
            manifest = await inventory(connection)
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        executable("pg_dump", bin_dir),
                        "--format=custom",
                        "--no-password",
                        "--snapshot=" + snapshot,
                        "--dbname=" + safe,
                    ],
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    env=env,
                    timeout=300,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            if result.returncode:
                raise RuntimeError("pg_dump failed; destination was not created")
        manifest.update(
            {
                "format": "ai-mos-postgresql-v1",
                "source_database": unquote(urlsplit(url).path.strip("/")),
                "sha256": hashlib.sha256(temporary.read_bytes()).hexdigest(),
            }
        )
        os.link(temporary, destination)  # Exclusive creation; never replace another backup.
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        await connection.close()
        if temporary:
            temporary.unlink(missing_ok=True)


async def restore(source, target_url, bin_dir=None):
    source = await asyncio.to_thread(Path(source).resolve)
    manifest = json.loads(source.with_suffix(source.suffix + ".manifest.json").read_text())
    if manifest.get("format") != "ai-mos-postgresql-v1" or hashlib.sha256(
        source.read_bytes()
    ).hexdigest() != manifest.get("sha256"):
        raise ValueError("Backup checksum or format mismatch")
    if unquote(urlsplit(target_url).path.strip("/")) == manifest["source_database"]:
        raise ValueError("Restore requires a different database name")
    safe, env = connection_args(target_url)
    connection = await asyncpg.connect(target_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await require_backup_role(connection)
        if await connection.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='public'"):
            raise ValueError("Restore destination must be empty")
        # Cluster roles are not included in pg_dump. Bootstrap restrictive role identities.
        for role in ["ai_mos_app", "ai_mos_worker", "ai_mos_queue"]:
            if not await connection.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role):
                await connection.execute(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS")
        await connection.execute("GRANT ai_mos_app TO ai_mos_worker")
        result = await asyncio.to_thread(
            subprocess.run,
            [
                executable("pg_restore", bin_dir),
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-password",
                "--dbname=" + safe,
                str(source),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise RuntimeError("pg_restore failed; restore transaction rolled back")
        # --no-owner must not leave queue security-definer functions owned by a superuser.
        async with connection.transaction():
            await connection.execute("GRANT CREATE ON SCHEMA public TO ai_mos_queue")
            for name, args in [
                ("claim_next_task", ""),
                ("claim_next_enrollment", ""),
                ("claim_next_effect", ""),
                ("claim_next_inbox", ""),
                ("resolve_checkout_org", "text"),
            ]:
                await connection.execute(f"ALTER FUNCTION {name}({args}) OWNER TO ai_mos_queue")
            await connection.execute("REVOKE CREATE ON SCHEMA public FROM ai_mos_queue")
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            restored = await inventory(connection)
        if (
            restored["counts"] != manifest["counts"]
            or restored["audit_sha256"] != manifest["audit_sha256"]
        ):
            raise ValueError("Restore verification failed")
        return {
            "status": "verified",
            "counts": restored["counts"],
            "audit_sha256": restored["audit_sha256"],
        }
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("path")
    parser.add_argument("--bin-dir")
    args = parser.parse_args()
    url = os.environ.get(
        "BACKUP_DATABASE_URL" if args.operation == "backup" else "RESTORE_DATABASE_URL"
    )
    if not url:
        raise SystemExit("Set BACKUP_DATABASE_URL or RESTORE_DATABASE_URL privately")
    result = asyncio.run(
        backup(url, args.path, args.bin_dir)
        if args.operation == "backup"
        else restore(args.path, url, args.bin_dir)
    )
    print(json.dumps(result, indent=2))
