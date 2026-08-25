"""Shared pytest fixtures.

Tests run fully offline against a file-backed SQLite database. Environment is
configured before the app is imported so module-level config (JWT secret, DB
URL) picks up test values.
"""

import os
import tempfile

import pytest

# --- configure environment BEFORE importing the app -------------------------
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".sqlite3")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("YOUTUBE_API_KEY", "")

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Recreate all tables before each test for isolation."""
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    yield
    database.Base.metadata.drop_all(bind=database.engine)


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """A TestClient already registered + authenticated as a default user."""
    client.post("/api/v1/auth/register", json={
        "email": "owner@example.com",
        "username": "owner",
        "password": "supersecret123",
    })
    resp = client.post("/api/v1/auth/login", data={
        "username": "owner@example.com",
        "password": "supersecret123",
    })
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def teardown_module():  # pragma: no cover
    try:
        os.remove(_DB_PATH)
    except OSError:
        pass
