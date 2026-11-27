"""The migrated PostgreSQL schema must match the SQLAlchemy metadata.

Catches the drift that local development hides: a column added to a model but
not to migrations/000N_*.sql works on a create_all database and fails only when
validation runs the real migrator. Set AI_MOS_TEST_ADMIN_URL to enable.

Set AI_MOS_SCHEMA_STRICT=1 to also fail on tables or columns that exist in the
database but not in the metadata (default: reported, not fatal), because some
migrations create helper tables deliberately.
"""

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

import app.growth.models  # noqa: F401  (registers growth tables on the shared metadata)
from app.migrate import upgrade
from app.models import Base

ADMIN = os.environ.get("AI_MOS_TEST_ADMIN_URL")
STRICT = os.environ.get("AI_MOS_SCHEMA_STRICT") == "1"

pytestmark = pytest.mark.skipif(not ADMIN, reason="Native PostgreSQL admin URL not supplied")

FAMILIES = [
    ("character varying", "text"),
    ("character", "text"),
    ("text", "text"),
    ("integer", "integer"),
    ("bigint", "integer"),
    ("smallint", "integer"),
    ("double precision", "float"),
    ("real", "float"),
    ("numeric", "numeric"),
    ("boolean", "bool"),
    ("timestamp", "timestamp"),
    ("date", "timestamp"),
    ("json", "json"),
    ("uuid", "uuid"),
    ("bytea", "binary"),
]

SA_TYPES = {
    "String": "text",
    "Text": "text",
    "Unicode": "text",
    "Integer": "integer",
    "BigInteger": "integer",
    "SmallInteger": "integer",
    "Float": "float",
    "Numeric": "numeric",
    "Boolean": "bool",
    "DateTime": "timestamp",
    "Date": "timestamp",
    "JSON": "json",
    "Uuid": "uuid",
    "LargeBinary": "binary",
}


def family_of_postgres(type_name):
    lowered = type_name.lower()
    for prefix, family in FAMILIES:
        if lowered.startswith(prefix):
            return family
    return lowered


def family_of_model(column):
    return SA_TYPES.get(type(column.type).__name__, type(column.type).__name__.lower())


@pytest.fixture(scope="module")
def migrated_schema():
    name = "ai_mos_schema_" + uuid4().hex

    async def setup():
        conn = await asyncpg.connect(ADMIN)
        try:
            await conn.execute(f'CREATE DATABASE "{name}"')
        finally:
            await conn.close()
        url = ADMIN.rsplit("/", 1)[0] + "/" + name
        await upgrade(url)
        conn = await asyncpg.connect(url)
        try:
            columns = await conn.fetch(
                "SELECT table_name, column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_schema = 'public'"
            )
            primary_keys = await conn.fetch(
                "SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'"
            )
        finally:
            await conn.close()
        return columns, primary_keys

    async def cleanup():
        conn = await asyncpg.connect(ADMIN)
        try:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                name,
            )
            await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        finally:
            await conn.close()

    columns, primary_keys = asyncio.run(setup())
    try:
        yield {
            "columns": {(row["table_name"], row["column_name"]): row for row in columns},
            "tables": {row["table_name"] for row in columns},
            "primary_keys": {(row["table_name"], row["column_name"]) for row in primary_keys},
        }
    finally:
        asyncio.run(cleanup())


def test_every_model_column_exists_in_the_migrated_schema(migrated_schema):
    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in migrated_schema["tables"]:
            problems.append(f"{table.name}: table missing from migrations")
            continue
        for column in table.columns:
            actual = migrated_schema["columns"].get((table.name, column.name))
            if actual is None:
                problems.append(
                    f"{table.name}.{column.name}: in model, missing from migrations "
                    "(add an ALTER TABLE to migrations/)"
                )
                continue
            expected_family = family_of_model(column)
            actual_family = family_of_postgres(actual["data_type"])
            if expected_family != actual_family:
                problems.append(
                    f"{table.name}.{column.name}: model expects {expected_family}, "
                    f"database has {actual['data_type']} ({actual_family})"
                )
            if column.primary_key:
                continue
            model_nullable = bool(column.nullable)
            database_nullable = actual["is_nullable"] == "YES"
            if model_nullable != database_nullable:
                problems.append(
                    f"{table.name}.{column.name}: model nullable={model_nullable}, "
                    f"database nullable={database_nullable}"
                )
    assert not problems, "Schema drift between models and migrations:\n  " + "\n  ".join(problems)


def test_primary_keys_match(migrated_schema):
    problems = []
    for table in Base.metadata.sorted_tables:
        expected = {(table.name, column.name) for column in table.columns if column.primary_key}
        if not expected:
            continue
        actual = {pair for pair in migrated_schema["primary_keys"] if pair[0] == table.name}
        if expected != actual:
            problems.append(f"{table.name}: model {sorted(expected)} vs database {sorted(actual)}")
    assert not problems, "Primary key drift:\n  " + "\n  ".join(problems)


def test_database_has_no_undocumented_columns(migrated_schema):
    documented = {
        (table.name, column.name) for table in Base.metadata.tables.values() for column in table.columns
    }
    undocumented = sorted(set(migrated_schema["columns"]) - documented)
    if not undocumented:
        return
    listing = "\n  ".join(f"{table}.{column}" for table, column in undocumented)
    if STRICT:
        pytest.fail(f"Columns exist in the database but not in models:\n  {listing}")
    print(f"\nNote: {len(undocumented)} columns exist in the database but not in models:\n  {listing}")
