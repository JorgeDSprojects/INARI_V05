import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d dashboard_postgres)"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_status_reports_unavailable_when_no_provider_configured(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider_type", "none")
    response = client.get("/chat/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"]


def test_create_session_returns_an_id(client: TestClient):
    response = client.post("/chat/sessions")
    assert response.status_code == 201
    assert "id" in response.json()


def test_get_session_returns_empty_history_for_a_new_session(client: TestClient):
    created = client.post("/chat/sessions").json()

    response = client.get(f"/chat/sessions/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["dashboard_id"] is None
    assert body["messages"] == []


def test_get_unknown_session_returns_404(client: TestClient):
    response = client.get("/chat/sessions/does-not-exist")
    assert response.status_code == 404


def test_send_message_returns_503_when_provider_unavailable(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider_type", "none")
    created = client.post("/chat/sessions").json()

    response = client.post(f"/chat/sessions/{created['id']}/messages", json={"message": "hola"})
    assert response.status_code == 503
