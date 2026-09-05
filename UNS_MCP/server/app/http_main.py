# UNS_MCP/server/app/http_main.py
"""HTTP entrypoint. Wraps app.server's shared MCP tool definitions in an
API-key check and serves them over streamable-http via uvicorn. Not used
for stdio -- that path runs `mcp run app/server.py` directly (see README),
bypassing this file entirely, since stdio needs no auth wrapping.
"""
from __future__ import annotations

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from app.auth import ApiKeyMiddleware
from app.config import load_settings
from app.server import mcp


def build_app():
    settings = load_settings()
    # The guard lives here, not in main(): `app = build_app()` runs at import
    # time, so serving this module directly (`uvicorn app.http_main:app`)
    # never calls main() and would otherwise skip the check entirely.
    if settings.mcp_api_key == "changeme-local-dev-key" and not settings.allow_default_api_key:
        raise SystemExit(
            "MCP_API_KEY is still the default value. Set a real key in .env, or set "
            "MCP_ALLOW_DEFAULT_KEY=true to explicitly accept the risk for local testing."
        )
    # Passing transport_security explicitly is required: streamable_http_app()
    # defaults host="127.0.0.1", which auto-enables loopback-only Host
    # validation and 421s every container-to-container call.
    app = mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=settings.allowed_origins,
        )
    )
    app.add_middleware(ApiKeyMiddleware, api_key=settings.mcp_api_key)
    return app


app = build_app()


def main() -> None:
    settings = load_settings()
    uvicorn.run(app, host=settings.http_host, port=settings.http_port)


if __name__ == "__main__":
    main()
