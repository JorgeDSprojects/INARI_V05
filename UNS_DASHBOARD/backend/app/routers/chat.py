# UNS_DASHBOARD/backend/app/routers/chat.py
"""The chat HTTP surface. See
docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 3.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionCreated,
    ChatSessionRead,
    ChatStatus,
)
from app.services import chat_agent
from app.services.llm_providers.openai_compatible import OpenAICompatibleProvider

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_provider():
    if settings.llm_provider_type == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key, model=settings.llm_model
        )
    return None


@router.get("/status", response_model=ChatStatus)
async def chat_status():
    if settings.llm_provider_type == "none":
        return ChatStatus(available=False, provider_type=None, reason="No LLM provider configured")

    if settings.llm_provider_type == "openai_compatible":
        # Assumes the endpoint exposes the standard OpenAI /v1/models path
        # (true for Ollama's compat layer per its docs, and for vLLM/OpenAI/
        # OpenRouter) -- verify with a real curl against whatever LLM_BASE_URL
        # is actually configured before trusting this in Task 9's live check;
        # if it 404s against a real target, swap to a lighter probe (e.g. a
        # bare TCP connect, or that endpoint's actual health path).
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                resp = await http_client.get(settings.llm_base_url.rstrip("/") + "/models")
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return ChatStatus(available=False, provider_type="openai_compatible", reason=f"Provider unreachable: {exc}")
        return ChatStatus(available=True, provider_type="openai_compatible", reason=None)

    return ChatStatus(available=False, provider_type=settings.llm_provider_type, reason="Provider type not yet implemented")


@router.post("/sessions", response_model=ChatSessionCreated, status_code=201)
async def create_session(db: AsyncSession = Depends(get_db)):
    session = ChatSession()
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionCreated(id=session.id)


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id).options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionRead(dashboard_id=session.dashboard_id, messages=session.messages)


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(session_id: str, body: ChatMessageRequest, db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    provider = _build_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail="No LLM provider is available")

    history_result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    history = [m.content for m in history_result.scalars().all()]

    try:
        reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(db, provider, history, body.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"LLM provider failed: {exc}") from exc

    for msg in new_messages:
        db.add(ChatMessage(session_id=session_id, role=msg["role"], content=msg))

    if dashboard_id and not session.dashboard_id:
        session.dashboard_id = dashboard_id

    await db.commit()

    return ChatMessageResponse(reply=reply, dashboard_id=session.dashboard_id, actions=actions)
