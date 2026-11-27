import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app


def test_settings_refuse_to_boot_without_required_keys(monkeypatch):
    for key in ("DATABASE_URL", "REDIS_URL", "OPENROUTER_API_KEY", "TOKEN_ENCRYPTION_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_healthz_reports_dependency_state():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["checks"]) == {"database", "redis"}
