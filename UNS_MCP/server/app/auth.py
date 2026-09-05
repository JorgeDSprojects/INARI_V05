"""Shared-API-key gate for the HTTP transport. stdio has no equivalent --
trust comes from the user having launched the process locally themselves.

See docs/superpowers/specs/2026-09-05-uns-mcp-design.md, Section 4.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.headers.get("X-MCP-API-Key") != self._api_key:
            return PlainTextResponse("Unauthorized", status_code=401)
        return await call_next(request)
