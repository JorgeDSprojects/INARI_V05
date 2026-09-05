import os

import pytest

from app.services import mcp_client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL")
MCP_API_KEY = os.environ.get("MCP_API_KEY")

pytestmark = pytest.mark.skipif(
    not MCP_SERVER_URL or not MCP_API_KEY,
    reason="MCP_SERVER_URL and MCP_API_KEY must both be set to a live UNS_MCP instance",
)


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "mcp_server_url", MCP_SERVER_URL)
    monkeypatch.setattr(settings, "mcp_api_key", MCP_API_KEY)


@pytest.mark.asyncio
async def test_list_read_tools_returns_all_four_uns_mcp_tools():
    tools = await mcp_client.list_read_tools()
    names = {t["function"]["name"] for t in tools}
    assert names == {"get_current_value", "get_historical_trend", "list_signals", "list_active_alarms"}
    for t in tools:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


@pytest.mark.asyncio
async def test_call_read_tool_returns_structured_content_for_list_signals():
    result = await mcp_client.call_read_tool("list_signals", {"topic_prefix": ""})
    assert isinstance(result, (list, dict))


@pytest.mark.asyncio
async def test_call_read_tool_raises_for_a_not_found_signal():
    with pytest.raises(Exception):
        await mcp_client.call_read_tool("get_current_value", {"topic": "pytest/nope", "signal_key": "nope"})


@pytest.mark.asyncio
async def test_wrong_api_key_fails(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "mcp_api_key", "definitely-wrong-key")
    with pytest.raises(Exception):
        await mcp_client.list_read_tools()
