"""Environment-variable configuration for the MCP query server."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    silver_database_url: str
    mcp_api_key: str
    http_host: str
    http_port: int
    # DNS-rebinding protection for the streamable-http transport. These must
    # be set explicitly: left to the SDK's own default, the transport allows
    # loopback Host headers only and answers every container-to-container
    # call with HTTP 421.
    allowed_hosts: list[str]
    allowed_origins: list[str]
    allow_default_api_key: bool


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        silver_database_url=e.get(
            "SILVER_DATABASE_URL",
            "postgresql://silver_reader:silverreaderpassword@uns_silver_postgres:5432/uns_silver",
        ),
        mcp_api_key=e.get("MCP_API_KEY", "changeme-local-dev-key"),
        http_host=e.get("HTTP_HOST", "0.0.0.0"),
        http_port=int(e.get("HTTP_PORT", "8000")),
        allowed_hosts=[h.strip() for h in e.get(
            "MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,[::1]:*,uns_mcp_server:*"
        ).split(",") if h.strip()],
        allowed_origins=[o.strip() for o in e.get(
            "MCP_ALLOWED_ORIGINS", "http://localhost:*,http://127.0.0.1:*,http://[::1]:*"
        ).split(",") if o.strip()],
        allow_default_api_key=e.get("MCP_ALLOW_DEFAULT_KEY", "false").strip().lower() == "true",
    )
