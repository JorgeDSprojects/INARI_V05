# UNS_DASHBOARD/backend/app/services/llm_providers/openai_compatible.py
"""Adapter for any OpenAI-compatible chat-completions endpoint: Ollama
(local or remote), vLLM, OpenAI itself, and OpenRouter all speak this
same wire format -- only base_url/api_key/model differ.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 5.
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.services.llm_providers.base import ProviderResponse, ToolCall


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str, client: object | None = None):
        self._client = client or AsyncOpenAI(base_url=base_url, api_key=api_key or "unused")
        self._model = model

    async def send(self, messages: list[dict], tools: list[dict]) -> ProviderResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools or None,
        )
        message = response.choices[0].message
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments))
            for tc in (message.tool_calls or [])
        ]
        # Some OpenAI-compatible backends (observed live against Ollama's
        # qwen2.5:14b-instruct) intermittently return non-empty/garbled
        # `content` alongside a valid `tool_calls` array. ProviderResponse.is_final
        # already keys off tool_calls (not content) so loop correctness doesn't
        # depend on this, but we still discard `text` whenever tool_calls are
        # present so callers never surface garbled text to the user/history.
        text = message.content if not tool_calls else None
        return ProviderResponse(text=text, tool_calls=tool_calls)
