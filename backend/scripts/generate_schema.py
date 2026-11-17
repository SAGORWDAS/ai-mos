"""Generate the initial migration while designing v0.3; applied migrations are immutable."""

import json
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Float, Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.growth import models as growth_models  # noqa: F401
from app.models import Base

root = Path(__file__).resolve().parents[1]
dialect = postgresql.dialect()
tables = Base.metadata.sorted_tables
tenant_tables = [table for table in tables if "organization_id" in table.c]
sql = [
    "-- Initial application schema; apply through python -m app.migrate upgrade.",
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_mos_app') THEN "
    "CREATE ROLE ai_mos_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$;",
    "REVOKE CREATE ON SCHEMA public FROM PUBLIC;",
]
for table in tables:
    sql.append(str(CreateTable(table).compile(dialect=dialect)) + ";")
    for index in sorted(table.indexes, key=lambda item: item.name):
        sql.append(str(CreateIndex(index).compile(dialect=dialect)) + ";")
for table in tenant_tables:
    name = table.name
    if "id" in table.c:
        sql.append(
            f"ALTER TABLE {name} ADD CONSTRAINT {name}_tenant_identity "
            "UNIQUE (organization_id, id);"
        )
for table in tenant_tables:
    name = table.name
    for column in table.c:
        for reference in column.foreign_keys:
            parent = reference.column.table
            if (
                column.name != "organization_id"
                and "organization_id" in parent.c
                and "id" in parent.c
            ):
                sql.append(
                    f"ALTER TABLE {name} ADD CONSTRAINT fk_{name}_{column.name}_tenant "
                    f"FOREIGN KEY (organization_id, {column.name}) "
                    f"REFERENCES {parent.name}(organization_id, id);"
                )
    predicate = "organization_id = NULLIF(current_setting('app.current_org', true), '')"
    if name == "sessions":
        predicate = f"({predicate} OR token_hash = current_setting('app.session_hash', true))"
    elif name == "memberships":
        predicate = f"({predicate} OR user_id = current_setting('app.current_user', true))"
    elif name == "invitations":
        predicate = (
            f"({predicate} OR email = (SELECT email FROM users WHERE id = "
            "current_setting('app.current_user', true)))"
        )
    sql.extend(
        [
            f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;",
            f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY;",
            f"CREATE POLICY tenant_isolation ON {name} TO ai_mos_app "
            f"USING ({predicate}) WITH CHECK ({predicate});",
        ]
    )
sql.extend(
    [
        "GRANT USAGE ON SCHEMA public TO ai_mos_app;",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_mos_app;",
        "REVOKE ALL ON schema_migrations FROM ai_mos_app;",
        "REVOKE UPDATE, DELETE ON audit_logs, payments, model_usage FROM ai_mos_app;",
    ]
)
# model_usage settlement is a trusted gateway operation; use a separate gateway role in deployment.
sql.append("GRANT UPDATE ON model_usage TO ai_mos_app;")
destination = root / "migrations"
destination.mkdir(exist_ok=True)
(destination / "0001_initial.sql").write_text("\n\n".join(sql) + "\n", encoding="utf-8")

# Isolated synthetic fixtures used to verify all tenant tables inside PostgreSQL itself.
fixtures = {"organizations": [], "tenants": [], "rows": []}
for label in ["a", "b"]:
    identities = {table.name: str(uuid4()) for table in tables if "id" in table.c}
    org_id, user_id = identities["organizations"], identities["users"]
    fixtures["organizations"].append(org_id)
    fixtures["tenants"].append({"organization_id": org_id, "user_id": user_id})
    for table in tables:
        row = {}
        for column in table.c:
            key = column.name
            if key == "organization_id":
                value = org_id
            elif key == "id":
                value = identities[table.name]
            elif column.foreign_keys:
                value = identities[next(iter(column.foreign_keys)).column.table.name]
            elif isinstance(column.type, Boolean):
                value = False
            elif isinstance(column.type, Integer):
                value = 1
            elif isinstance(column.type, Float):
                value = time.time() + (86400 if "expires" in key else 0)
            elif isinstance(column.type, JSON):
                value = "{}"
            else:
                value = f"{label}-{key}"[: column.type.length or 100]
            row[key] = value
        fixtures["rows"].append({"table": table.name, "values": row})
(destination / "isolation-fixtures.json").write_text(json.dumps(fixtures), encoding="utf-8")
print(f"Generated {len(tables)} tables, {len(tenant_tables)} forced-RLS policies")
