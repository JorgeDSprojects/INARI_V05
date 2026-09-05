# UNS_MCP/server/app/http_main.py
"""HTTP entrypoint. Wraps app.server's shared MCP tool definitions in an
API-key check and serves them over streamable-http via uvicorn. Not used
for stdio -- that path runs `mcp run app/server.py` directly (see README),
bypassing this file entirely, since stdio needs no auth wrapping.
"""
from __future__ import annotations

import uvicorn

from app.auth import ApiKeyMiddleware
from app.config import load_settings
from app.server import mcp


def build_app():
    app = mcp.streamable_http_app()
    app.add_middleware(ApiKeyMiddleware, api_key=load_settings().mcp_api_key)
    return app


app = build_app()


def main() -> None:
    settings = load_settings()
    uvicorn.run(app, host=settings.http_host, port=settings.http_port)


if __name__ == "__main__":
    main()
