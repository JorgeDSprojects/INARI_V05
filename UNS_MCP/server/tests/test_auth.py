from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.auth import ApiKeyMiddleware


def _make_app(api_key: str) -> Starlette:
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/ping", ok)])
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)
    return app


def test_request_with_correct_key_passes_through():
    client = TestClient(_make_app("secret"))
    response = client.get("/ping", headers={"X-MCP-API-Key": "secret"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_request_with_wrong_key_is_rejected():
    client = TestClient(_make_app("secret"))
    response = client.get("/ping", headers={"X-MCP-API-Key": "wrong"})
    assert response.status_code == 401


def test_request_with_missing_key_is_rejected():
    client = TestClient(_make_app("secret"))
    response = client.get("/ping")
    assert response.status_code == 401
