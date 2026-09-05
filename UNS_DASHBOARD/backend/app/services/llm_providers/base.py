# UNS_DASHBOARD/backend/app/services/llm_providers/base.py
"""Provider-agnostic shapes for the chat agent's tool-calling loop.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class LLMProvider(Protocol):
    async def send(self, messages: list[dict], tools: list[dict]) -> ProviderResponse: ...
