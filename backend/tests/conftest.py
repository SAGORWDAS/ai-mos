"""Tests build isolated temporary databases; never use the developer's data.

`clients` is unchanged (SQLite). `db_clients` is the same pair of clients but
parametrised over SQLite and, when AI_MOS_TEST_ADMIN_URL is set, native
PostgreSQL. Migrate tests to `db_clients` file by file; leave tests that read
the SQLite file directly on `clients`.
"""

import asyncio
import os
from contextlib import contextmanager
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.migrate import upgrade

ADMIN = os.environ.get("AI_MOS_TEST_ADMIN_URL")
DIALECTS = ("sqlite", "postgres") if ADMIN else ("sqlite",)


def settings_for(database_url, worker_database_url=""):
    return Settings(
        database_url=database_url,
        worker_database_url=worker_database_url,
        worker_enabled=False,
        # Legacy HTTP contracts use fixture models; registry enforcement has its own tests.
        allow_unverified_models=True,
        token_encryption_key=Fernet.generate_key().decode(),
    )


@contextmanager
def paired(app):
    with TestClient(app) as a:
        b = TestClient(app)
        b.portal = a.portal
        try:
            yield a, b
        finally:
            b.close()


def make_postgres_database():
    """Create a disposable database with API and worker logins; return urls and cleanup."""
    name = "ai_mos_test_" + uuid4().hex
    password = uuid4().hex
    api_role, worker_role = "api_" + uuid4().hex, "worker_" + uuid4().hex

    async def setup():
        conn = await asyncpg.connect(ADMIN)
        try:
            await conn.execute(f'CREATE DATABASE "{name}"')
        finally:
            await conn.close()
        database_url = ADMIN.rsplit("/", 1)[0] + "/" + name
        await upgrade(database_url)
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute(
                f"CREATE ROLE {api_role} LOGIN PASSWORD '{password}' IN ROLE ai_mos_app"
            )
            await conn.execute(
                f"CREATE ROLE {worker_role} LOGIN PASSWORD '{password}' IN ROLE ai_mos_worker"
            )
        finally:
            await conn.close()
        parsed = urlsplit(ADMIN)
        base = f"@{parsed.hostname}:{parsed.port or 5432}/{name}"
        return (
            f"postgresql+asyncpg://{api_role}:{password}{base}",
            f"postgresql+asyncpg://{worker_role}:{password}{base}",
        )

    async def cleanup():
        conn = await asyncpg.connect(ADMIN)
        try:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                name,
            )
            await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in (api_role, worker_role):
                await conn.execute(f"DROP ROLE IF EXISTS {role}")
        finally:
            await conn.close()

    try:
        return asyncio.run(setup()), cleanup
    except BaseException:
        asyncio.run(cleanup())
        raise


@pytest.fixture
def clients(tmp_path):
    app = create_app(settings_for(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"))
    with paired(app) as pair:
        yield pair


@pytest.fixture(params=DIALECTS)
def db_clients(request, tmp_path):
    if request.param == "sqlite":
        app = create_app(settings_for(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"))
        with paired(app) as pair:
            yield pair
        return
    (api_url, worker_url), cleanup = make_postgres_database()
    try:
        app = create_app(settings_for(api_url, worker_url))
        with paired(app) as pair:
            yield pair
    finally:
        asyncio.run(cleanup())


@pytest.fixture
def pg_clients():
    if not ADMIN:
        pytest.skip("Native PostgreSQL admin URL not supplied")
    (api_url, worker_url), cleanup = make_postgres_database()
    try:
        with paired(create_app(settings_for(api_url, worker_url))) as pair:
            yield pair
    finally:
        asyncio.run(cleanup())
