import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import app.growth.models  # noqa: F401
from app.models import Base
from app.schema import assert_model_columns, upgrade_local


def test_sqlite_additive_upgrade_preserves_data_and_records_real_source_checksum(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    try:
        with engine.begin() as c:
            Base.metadata.create_all(c)
            c.exec_driver_sql("ALTER TABLE leads DROP COLUMN source_ref")
            c.exec_driver_sql("INSERT INTO organizations VALUES ('Saved org',0,'org-1',1)")
        with engine.begin() as c:
            upgrade_local(c)
            Base.metadata.create_all(c)
            assert_model_columns(c)
            expected = hashlib.sha256(
                (Path(__file__).parents[1] / "app/schema.py").read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            assert c.scalar(text("SELECT checksum FROM schema_migrations")) == expected
            assert c.scalar(text("SELECT name FROM organizations")) == "Saved org"
        with engine.begin() as c:
            c.exec_driver_sql("ALTER TABLE leads DROP COLUMN source_ref")
            with pytest.raises(RuntimeError, match="leads.source_ref"):
                assert_model_columns(c)
    finally:
        engine.dispose()
