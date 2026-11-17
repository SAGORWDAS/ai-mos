"""Non-destructive upgrades for the local SQLite development database."""

from sqlalchemy import inspect, text


def upgrade_local(connection):
    if connection.dialect.name != "sqlite":
        return
    tables = set(inspect(connection).get_table_names())
    # Own the SQLite DDL transaction so a failed upgrade rolls back the entire change.
    connection.exec_driver_sql("BEGIN IMMEDIATE")
    additions = {
        "leads": [
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("personalisation", "VARCHAR(400) NOT NULL DEFAULT ''"),
            ("personalisation_evidence", "VARCHAR(2000) NOT NULL DEFAULT ''"),
        ],
        "content_items": [("task_id", "VARCHAR(36) REFERENCES tasks(id)")],
        "brand_chunks": [
            ("embedding", "JSON NOT NULL DEFAULT '[]'"),
            ("embedding_model", "VARCHAR(200) NOT NULL DEFAULT ''"),
        ],
        "integrations": [
            ("sync_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
            ("sync_interval_minutes", "INTEGER NOT NULL DEFAULT 10"),
            ("sync_next_at", "FLOAT NOT NULL DEFAULT 0"),
            ("sync_cursor", "VARCHAR(2000) NOT NULL DEFAULT ''"),
            ("sync_last_at", "FLOAT NOT NULL DEFAULT 0"),
            ("sync_error", "VARCHAR(120) NOT NULL DEFAULT ''"),
        ],
        "model_usage": [
            ("cache_source_id", "VARCHAR(36) REFERENCES model_usage(id)"),
            ("reserved_micros", "INTEGER NOT NULL DEFAULT 0"),
            ("reservation_period", "VARCHAR(10) NOT NULL DEFAULT ''"),
            ("provider_ref", "VARCHAR(200) NOT NULL DEFAULT ''"),
            ("settled", "BOOLEAN NOT NULL DEFAULT 1"),
            ("reconciliation_evidence", "VARCHAR(1000) NOT NULL DEFAULT ''"),
        ],
        "users": [
            ("recovery_hash", "VARCHAR(64) NOT NULL DEFAULT ''"),
            ("totp_secret", "VARCHAR(2000) NOT NULL DEFAULT ''"),
            ("totp_pending", "VARCHAR(2000) NOT NULL DEFAULT ''"),
            ("totp_last_counter", "FLOAT NOT NULL DEFAULT -1"),
        ],
        "checkouts": [
            ("payment_ref", "VARCHAR(200) NOT NULL DEFAULT ''"),
            ("subscription_ref", "VARCHAR(200) NOT NULL DEFAULT ''"),
            ("url", "VARCHAR(2000) NOT NULL DEFAULT ''"),
            ("recurring", "BOOLEAN NOT NULL DEFAULT 0"),
        ],
        "customers": [("simulated", "BOOLEAN NOT NULL DEFAULT 1")],
        "effects": [("dispatch_started_at", "FLOAT")],
        "subscriptions": [
            ("provider_ref", "VARCHAR(200) NOT NULL DEFAULT ''"),
            ("last_event_at", "FLOAT NOT NULL DEFAULT 0"),
        ],
    }
    for table, fields in additions.items():
        if table not in tables:
            continue
        columns = {item["name"] for item in inspect(connection).get_columns(table)}
        for name, declaration in fields:
            if name not in columns:
                connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {declaration}'))
    if "content_items" in tables:
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS content_items_task_unique "
            "ON content_items(organization_id,task_id)"
        )
    if "subscriptions" in tables:
        unique = inspect(connection).get_unique_constraints("subscriptions")
        if any(item["column_names"] == ["organization_id", "customer_id"] for item in unique):
            from app.growth.models import Subscription

            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_subscriptions_organization_id")
            connection.exec_driver_sql(
                "ALTER TABLE subscriptions RENAME TO subscriptions_legacy_upgrade"
            )
            Subscription.__table__.create(connection)
            fields = ", ".join('"' + column.name + '"' for column in Subscription.__table__.columns)
            connection.exec_driver_sql(
                "INSERT INTO subscriptions ("
                + fields
                + ") SELECT "
                + fields
                + " FROM subscriptions_legacy_upgrade"
            )
            connection.exec_driver_sql("DROP TABLE subscriptions_legacy_upgrade")
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL)"
        )
    )
    connection.execute(
        text(
            "INSERT OR IGNORE INTO schema_migrations VALUES "
            "('sqlite-v4.1', 'additive-and-subscription-constraint-upgrade')"
        )
    )
