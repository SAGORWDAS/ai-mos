"""Fail-closed configuration and database checks for a controlled live pilot."""

import base64
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def configuration_checks(settings):
    parsed = urlsplit(settings.public_api_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    try:
        Fernet(settings.token_encryption_key.encode())
        encryption = len(set(base64.urlsafe_b64decode(settings.token_encryption_key))) >= 12
    except (ValueError, TypeError):
        encryption = False
    code = settings.validation_access_code
    try:
        password = make_url(settings.database_url).password or ""
        database_secret = (
            len(password) >= 20
            and len(set(password)) >= 8
            and not password.lower().startswith(("placeholder", "replace-", "your-"))
        )
    except (ValueError, ArgumentError):
        database_secret = False
    checks = [
        (
            "https",
            parsed.scheme == "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"},
            "Use a public HTTPS address with valid TLS.",
        ),
        ("cookies", settings.secure_cookies, "Enable secure session cookies."),
        (
            "origins",
            settings.allowed_origins == [origin],
            "Allow only the HTTPS website origin, without a path.",
        ),
        ("encryption", encryption, "Install a persistent, valid Fernet encryption key."),
        (
            "database_secret",
            database_secret,
            "Use a random private database password, at least 20 characters.",
        ),
        (
            "database",
            settings.database_url.startswith("postgresql+asyncpg://"),
            "Use a migrated PostgreSQL database with a restricted API login.",
        ),
        (
            "catalog",
            not settings.allow_unverified_models,
            "Require verified model catalog evidence.",
        ),
        (
            "pilot_access",
            len(code) >= 32
            and len(set(code)) >= 12
            and not code.lower().startswith(("placeholder", "replace-", "your-")),
            "Set a random private pilot signup code of at least 32 characters.",
        ),
        (
            "review",
            len(settings.validation_review_ref.strip()) >= 8
            and not settings.validation_review_ref.lower().startswith(("placeholder", "replace-")),
            "Record the operator's deployment review reference; this is not certification.",
        ),
    ]
    if settings.worker_enabled:
        checks.append(
            (
                "separate_worker",
                bool(settings.worker_database_url)
                and settings.worker_database_url != settings.database_url,
                "Use a separate restricted worker connection or a standalone worker.",
            )
        )
    return [{"id": name, "ready": bool(ready), "detail": detail} for name, ready, detail in checks]


def enforce_configuration(settings):
    if settings.app_env in {"development", "test"}:
        return
    if settings.app_env != "validation":
        raise RuntimeError("Production is gated on deployment review and live acceptance")
    missing = [c["id"] for c in configuration_checks(settings) if not c["ready"]]
    if missing:
        raise RuntimeError("validation_configuration_required:" + ",".join(missing))


async def database_checks(engine, *, worker=False):
    from app.models import Base

    if engine.dialect.name != "postgresql":
        return [
            {
                "id": "restricted_database",
                "ready": False,
                "detail": "Validation requires PostgreSQL runtime-role checks.",
            }
        ]
    async with engine.connect() as conn:
        role = (
            (
                await conn.execute(
                    text("""
            SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,
              pg_has_role(current_user,'ai_mos_app','MEMBER') AS app_member,
              pg_has_role(current_user,'ai_mos_worker','MEMBER') AS worker_member,
              has_schema_privilege(current_user,'public','CREATE') AS can_create
            FROM pg_roles WHERE rolname=current_user
        """)
                )
            )
            .mappings()
            .one()
        )
        tables = (
            (
                await conn.execute(
                    text("""
            SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,
              pg_has_role(current_user,c.relowner,'MEMBER') AS owns
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
        """)
                )
            )
            .mappings()
            .all()
        )
        columns = (
            await conn.execute(
                text("""
            SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema='public'
        """)
            )
        ).all()
        grants = (
            (
                await conn.execute(
                    text("""
            SELECT has_table_privilege(current_user,'audit_logs','UPDATE') OR
                   has_table_privilege(current_user,'audit_logs','DELETE') AS audit_write,
                   has_function_privilege(current_user,'claim_next_task()','EXECUTE') AS queue
        """)
                )
            )
            .mappings()
            .one()
        )
    actual = {row["relname"]: row for row in tables}
    expected = [t for t in Base.metadata.tables.values() if "organization_id" in t.c]
    available_columns = set(columns)
    schema = all(
        t.name in actual and all((t.name, c.name) in available_columns for c in t.c)
        for t in Base.metadata.tables.values()
    )
    rls = all(
        t.name in actual
        and actual[t.name]["relrowsecurity"]
        and actual[t.name]["relforcerowsecurity"]
        and not actual[t.name]["owns"]
        for t in expected
    )
    restricted = not any(
        role[k] for k in ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole", "can_create")
    )
    membership = role["app_member"] and bool(role["worker_member"]) == worker
    return [
        {
            "id": "runtime_role",
            "ready": restricted and membership,
            "detail": "Runtime login has the correct API/worker membership and no elevated flags.",
        },
        {
            "id": "schema",
            "ready": schema,
            "detail": "All application tables and columns are installed by the migrator.",
        },
        {
            "id": "tenant_rls",
            "ready": rls,
            "detail": f"Forced RLS and non-owner access cover {len(expected)} tenant tables.",
        },
        {
            "id": "grants",
            "ready": not grants["audit_write"] and bool(grants["queue"]) == worker,
            "detail": "Audit history is append-only; only workers can claim the global queue.",
        },
    ]


async def enforce_database(engine, *, worker=False):
    checks = await database_checks(engine, worker=worker)
    missing = [c["id"] for c in checks if not c["ready"]]
    if missing:
        raise RuntimeError("validation_database_preflight_failed:" + ",".join(missing))
    return checks


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-db", action="store_true")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    checks = configuration_checks(settings)

    async def inspect_database():
        engine = create_async_engine(settings.database_url, hide_parameters=True)
        try:
            return await database_checks(engine, worker=args.worker)
        except Exception:
            return [
                {
                    "id": "database_connection",
                    "ready": False,
                    "detail": "Database unavailable or required migrations/grants missing.",
                }
            ]
        finally:
            await engine.dispose()

    if args.check_db:
        checks.extend(asyncio.run(inspect_database()))
    print(json.dumps({"checks": checks, "production_approved": False}, indent=2))
    raise SystemExit(0 if all(c["ready"] for c in checks) else 1)
