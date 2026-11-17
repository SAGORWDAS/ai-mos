import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_local_boot_without_provider_keys(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'health.db'}")
    with TestClient(create_app(settings)) as client:
        result = client.get("/healthz")
        assert result.status_code == 200
        assert result.json()["checks"]["database"] is True


def test_production_is_gated():
    with pytest.raises(RuntimeError, match="Production is gated"):
        create_app(Settings(app_env="production"))
