import pytest
from starlette.testclient import TestClient


@pytest.fixture
def http_main(monkeypatch):
    """Import app.http_main with a non-default API key already in the env.

    Importing the module executes `app = build_app()` at module scope, and
    that call is exactly the guard under test -- so the import itself needs a
    real key to succeed before individual tests can drive build_app()
    themselves under whatever env they want.
    """
    monkeypatch.setenv("MCP_API_KEY", "import-time-real-key")
    from app import http_main as module

    return module


def test_build_app_refuses_to_start_with_the_default_api_key(http_main, monkeypatch):
    # The guard lives in build_app(), not main(), because `app = build_app()`
    # runs at import time -- serving `uvicorn app.http_main:app` directly
    # never calls main() and would otherwise skip the check entirely.
    monkeypatch.delenv("MCP_ALLOW_DEFAULT_KEY", raising=False)
    monkeypatch.setenv("MCP_API_KEY", "changeme-local-dev-key")
    with pytest.raises(SystemExit) as excinfo:
        http_main.build_app()
    assert "MCP_API_KEY" in str(excinfo.value)


def test_build_app_starts_when_default_key_is_explicitly_allowed(http_main, monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "changeme-local-dev-key")
    monkeypatch.setenv("MCP_ALLOW_DEFAULT_KEY", "true")
    assert http_main.build_app() is not None


def test_build_app_starts_with_a_real_key(http_main, monkeypatch):
    monkeypatch.delenv("MCP_ALLOW_DEFAULT_KEY", raising=False)
    monkeypatch.setenv("MCP_API_KEY", "a-real-key")
    assert http_main.build_app() is not None


_REQUEST = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
_HEADERS = {
    "X-MCP-API-Key": "a-real-key",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _post_with_host(app, host: str):
    # TestClient derives the Host header from base_url, which is exactly the
    # header the DNS-rebinding check inspects.
    with TestClient(app, base_url=f"http://{host}") as client:
        return client.post("/mcp", json=_REQUEST, headers=_HEADERS)


def test_non_loopback_host_header_is_accepted(http_main, monkeypatch):
    """The whole point of fix #1: a container-to-container call arriving with
    `Host: uns_mcp_server:8000` must not be rejected. Before the fix the SDK's
    loopback-only default answered 421 for every such call."""
    monkeypatch.setenv("MCP_API_KEY", "a-real-key")
    app = http_main.build_app()

    response = _post_with_host(app, "uns_mcp_server:8000")
    assert response.status_code != 421, response.text


def test_unlisted_host_header_is_still_rejected(http_main, monkeypatch):
    """The allow-list is an allow-list, not a free-for-all: the fix must not
    turn DNS-rebinding protection off."""
    monkeypatch.setenv("MCP_API_KEY", "a-real-key")
    app = http_main.build_app()

    response = _post_with_host(app, "evil.example.com")
    assert response.status_code == 421


def test_allowed_hosts_are_configurable(http_main, monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "a-real-key")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "somewhere.internal:*")

    # One app per request: the SDK's session manager refuses to run twice.
    assert _post_with_host(http_main.build_app(), "somewhere.internal:8000").status_code != 421
    assert _post_with_host(http_main.build_app(), "uns_mcp_server:8000").status_code == 421
