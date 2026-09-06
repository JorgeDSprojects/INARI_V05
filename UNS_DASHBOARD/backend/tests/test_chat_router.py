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


def _cleanup(client: TestClient):
    for d in client.get("/dashboards/").json():
        if d["name"].startswith("pytest"):
            client.delete(f"/dashboards/{d['id']}")


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


def test_create_session_bound_to_an_existing_dashboard(client: TestClient):
    _cleanup(client)
    dashboard = client.post("/dashboards/", json={"name": "pytest chat-bound dashboard"}).json()

    response = client.post("/chat/sessions", json={"dashboard_id": dashboard["id"]})
    assert response.status_code == 201
    session_id = response.json()["id"]

    detail = client.get(f"/chat/sessions/{session_id}").json()
    assert detail["dashboard_id"] == dashboard["id"]


def test_create_session_with_unknown_dashboard_id_returns_404(client: TestClient):
    response = client.post("/chat/sessions", json={"dashboard_id": "does-not-exist"})
    assert response.status_code == 404


def test_list_sessions_returns_empty_list_for_a_dashboard_with_no_sessions(client: TestClient):
    _cleanup(client)
    dashboard = client.post("/dashboards/", json={"name": "pytest chat-history-empty dashboard"}).json()

    response = client.get("/chat/sessions", params={"dashboard_id": dashboard["id"]})
    assert response.status_code == 200
    assert response.json() == []


def test_list_sessions_shows_a_session_with_its_first_user_message(client: TestClient, monkeypatch):
    from app.routers import chat as chat_router
    from app.services import mcp_client
    from app.services.llm_providers.base import ProviderResponse

    class _FakeProvider:
        async def send(self, messages, tools):
            return ProviderResponse(text="¡Hola!", tool_calls=[])

    # Sidestep the real LLM/MCP dependencies (chat_status already covers
    # those) so this test only exercises list_sessions' own logic: that it
    # reflects a session created through the real HTTP flow, with the first
    # user message run_turn actually persisted.
    monkeypatch.setattr(chat_router, "_build_provider", lambda: _FakeProvider())
    monkeypatch.setattr(mcp_client, "list_read_tools", lambda: _async_empty_list())

    _cleanup(client)
    dashboard = client.post("/dashboards/", json={"name": "pytest chat-history dashboard"}).json()
    session = client.post("/chat/sessions", json={"dashboard_id": dashboard["id"]}).json()

    sent = client.post(f"/chat/sessions/{session['id']}/messages", json={"message": "hola, quiero un gauge de RPM"})
    assert sent.status_code == 200

    response = client.get("/chat/sessions", params={"dashboard_id": dashboard["id"]})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == session["id"]
    assert body[0]["first_user_message"] == "hola, quiero un gauge de RPM"


async def _async_empty_list():
    return []


def test_send_message_rebinds_session_to_a_genuinely_new_dashboard(client: TestClient, monkeypatch):
    """Regression test for a bug found in review of Fix 1: a session can now
    start ALREADY bound to a dashboard (dashboard_id passed at creation). If
    the user then explicitly asks to create a SEPARATE, new dashboard and the
    model does so, the response (and the session) must reflect that NEW
    dashboard_id -- not silently keep pointing at the original one just
    because it was already truthy. See app/routers/chat.py's send_message.
    """
    from app.routers import chat as chat_router
    from app.services import mcp_client
    from app.services.llm_providers.base import ProviderResponse, ToolCall

    class _CreatesAnotherDashboardProvider:
        def __init__(self):
            self._calls = 0

        async def send(self, messages, tools):
            self._calls += 1
            if self._calls == 1:
                return ProviderResponse(
                    text=None,
                    tool_calls=[ToolCall(id="1", name="create_dashboard", arguments={"name": "pytest second dashboard"})],
                )
            return ProviderResponse(text="Listo, he creado el nuevo dashboard.", tool_calls=[])

    monkeypatch.setattr(chat_router, "_build_provider", lambda: _CreatesAnotherDashboardProvider())
    monkeypatch.setattr(mcp_client, "list_read_tools", lambda: _async_empty_list())

    _cleanup(client)
    original_dashboard = client.post("/dashboards/", json={"name": "pytest original dashboard"}).json()
    session = client.post("/chat/sessions", json={"dashboard_id": original_dashboard["id"]}).json()

    response = client.post(
        f"/chat/sessions/{session['id']}/messages",
        json={"message": "crea un dashboard nuevo llamado pytest second dashboard"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dashboard_id"] != original_dashboard["id"]

    new_dashboard = client.get(f"/dashboards/{body['dashboard_id']}").json()
    assert new_dashboard["name"] == "pytest second dashboard"

    detail = client.get(f"/chat/sessions/{session['id']}").json()
    assert detail["dashboard_id"] == body["dashboard_id"]
