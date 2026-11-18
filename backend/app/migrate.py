"""Versioned PostgreSQL schema runner. Use a dedicated migration connection."""

import argparse
import asyncio
import hashlib
import os
from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


async def plan(url):
    """Read pending files without creating tables, applying SQL or provisioning logins."""
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await connection.execute("SELECT pg_advisory_lock(7198321)")
        exists = await connection.fetchval("SELECT to_regclass('public.schema_migrations')")
        applied = (
            dict(await connection.fetch("SELECT version,checksum FROM schema_migrations"))
            if exists
            else {}
        )
        result = []
        for path in sorted(MIGRATIONS.glob("*.sql")):
            checksum = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
            if path.name in applied and applied[path.name] != checksum:
                raise RuntimeError(f"Applied migration changed: {path.name}")
            result.append(
                {
                    "version": path.name,
                    "checksum": checksum,
                    "status": "applied" if path.name in applied else "pending",
                }
            )
        unknown = set(applied) - {item["version"] for item in result}
        if unknown:
            raise RuntimeError("Applied migration files missing: " + ",".join(sorted(unknown)))
        return result
    finally:
        await connection.close()


async def upgrade(url):
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await connection.execute("SELECT pg_advisory_lock(7198321)")
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, checksum text NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            prior = await connection.fetchval(
                "SELECT checksum FROM schema_migrations WHERE version=$1", path.name
            )
            if prior:
                if prior != checksum:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations(version,checksum) VALUES($1,$2)",
                    path.name,
                    checksum,
                )
            print(f"Applied {path.name}")
        if os.environ.get("PROVISION_DATABASE_ROLES") == "true":
            for role, variable in [
                ("ai_mos_app", "APP_DATABASE_PASSWORD"),
                ("ai_mos_worker", "WORKER_DATABASE_PASSWORD"),
            ]:
                password = os.environ.get(variable)
                if not password:
                    raise RuntimeError(f"Set {variable} before provisioning runtime roles")
                statement = await connection.fetchval(
                    "SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', "
                    "$1::text, $2::text)",
                    role,
                    password,
                )
                await connection.execute(statement)
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["upgrade", "plan"])
    args = parser.parse_args()
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgresql+asyncpg://")):
        raise SystemExit(
            "Set MIGRATION_DATABASE_URL to the dedicated PostgreSQL migrator connection"
        )
    if args.command == "plan":
        import json

        print(json.dumps(asyncio.run(plan(url)), indent=2))
    else:
        asyncio.run(upgrade(url))
