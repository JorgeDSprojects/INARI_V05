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
    )
