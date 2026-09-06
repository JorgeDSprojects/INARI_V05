from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatStatus(BaseModel):
    available: bool
    provider_type: str | None
    reason: str | None


class ChatSessionCreate(BaseModel):
    dashboard_id: str | None = None


class ChatSessionCreated(BaseModel):
    id: str


class ChatSessionSummary(BaseModel):
    id: str
    created_at: datetime
    first_user_message: str | None


class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    reply: str
    dashboard_id: str | None
    actions: list[str]


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: dict[str, Any]


class ChatSessionRead(BaseModel):
    dashboard_id: str | None
    messages: list[ChatMessageRead]
