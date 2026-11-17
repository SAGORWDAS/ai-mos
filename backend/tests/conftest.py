"""Tests build isolated temporary databases; never use the developer's data."""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def clients(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
            worker_enabled=False,
            # Legacy HTTP contracts use fixture models; registry enforcement has its own tests.
            allow_unverified_models=True,
            token_encryption_key=Fernet.generate_key().decode(),
        )
    )
    with TestClient(app) as a:
        b = TestClient(app)
        b.portal = a.portal
        try:
            yield a, b
        finally:
            b.close()
