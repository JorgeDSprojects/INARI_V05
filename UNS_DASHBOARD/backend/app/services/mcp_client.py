"""Thin MCP-client wrapper around UNS_MCP's four read tools.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 1 and Section 4.

Note on the HTTP client: the installed `mcp` SDK (2.1.1) types
`streamable_http_client`'s `http_client` parameter as `httpx2.AsyncClient |
None`, not `httpx.AsyncClient` -- the SDK's own dependency, `httpx2`
("the next generation HTTP client", a separate PyPI package by the httpx/
pydantic authors), not the classic `httpx` package this project also
depends on for other things. Verified live via:

    python -c "import mcp.client.streamable_http as m; help(m.streamable_http_client)"

so this module uses `httpx2.AsyncClient` to attach the `X-MCP-API-Key`
header, and `httpx2` is listed in requirements.txt alongside `mcp`.
"""
from __future__ import annotations

from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.config import settings


async def list_read_tools() -> list[dict]:
    async with httpx2.AsyncClient(headers={"X-MCP-API-Key": settings.mcp_api_key}) as http_client:
        transport = streamable_http_client(settings.mcp_server_url, http_client=http_client)
        async with Client(transport) as client:
            result = await client.list_tools()
            return [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in result.tools
            ]


async def call_read_tool(name: str, arguments: dict[str, Any]) -> Any:
    async with httpx2.AsyncClient(headers={"X-MCP-API-Key": settings.mcp_api_key}) as http_client:
        transport = streamable_http_client(settings.mcp_server_url, http_client=http_client)
        async with Client(transport) as client:
            result = await client.call_tool(name, arguments)
            if result.is_error:
                text = " ".join(b.text for b in result.content if hasattr(b, "text"))
                raise RuntimeError(text or f"MCP tool {name} failed")
            return result.structured_content
