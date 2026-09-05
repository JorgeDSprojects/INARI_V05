import json
from types import SimpleNamespace

import pytest

from app.services.llm_providers.openai_compatible import OpenAICompatibleProvider


class _FakeCompletions:
    def __init__(self, response):
        self._response = response

    async def create(self, **kwargs):
        self.last_call = kwargs
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeClient:
    def __init__(self, response):
        self.chat = _FakeChat(response)


def _make_response(content, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_send_returns_final_text_when_no_tool_calls():
    response = _make_response("Hola, ¿en qué puedo ayudarte?", tool_calls=None)
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="m", client=_FakeClient(response))

    result = await provider.send(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert result.is_final
    assert result.text == "Hola, ¿en qué puedo ayudarte?"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_send_parses_tool_calls_and_decodes_json_arguments():
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="list_signals", arguments=json.dumps({"topic_prefix": "T01"})),
    )
    response = _make_response(None, tool_calls=[tool_call])
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="m", client=_FakeClient(response))

    result = await provider.send(messages=[], tools=[])

    assert not result.is_final
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "list_signals"
    assert result.tool_calls[0].arguments == {"topic_prefix": "T01"}


@pytest.mark.asyncio
async def test_send_passes_model_messages_and_tools_through():
    response = _make_response("ok", tool_calls=None)
    fake_client = _FakeClient(response)
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="qwen2.5:14b-instruct", client=fake_client)

    messages = [{"role": "user", "content": "hola"}]
    tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]
    await provider.send(messages, tools)

    assert fake_client.chat.completions.last_call["model"] == "qwen2.5:14b-instruct"
    assert fake_client.chat.completions.last_call["messages"] == messages
    assert fake_client.chat.completions.last_call["tools"] == tools


@pytest.mark.asyncio
async def test_send_passes_none_for_tools_when_empty():
    response = _make_response("ok", tool_calls=None)
    fake_client = _FakeClient(response)
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="m", client=fake_client)

    await provider.send(messages=[], tools=[])

    assert fake_client.chat.completions.last_call["tools"] is None
