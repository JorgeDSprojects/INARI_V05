# UNS_DASHBOARD/backend/app/routers/chat.py
"""The chat HTTP surface. See
docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 3.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.dashboard import Dashboard
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionCreated,
    ChatSessionRead,
    ChatSessionSummary,
    ChatStatus,
)
from app.services import chat_agent, mcp_client
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
        # OpenRouter) -- verified live in Task 9 against the real target.
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                resp = await http_client.get(settings.llm_base_url.rstrip("/") + "/models")
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:  # noqa: BLE001
            return ChatStatus(available=False, provider_type="openai_compatible", reason=f"Provider unreachable: {exc}")

        # A 2xx /models response isn't enough on its own -- the endpoint can be
        # up while the configured model was never pulled/loaded. Ollama/vLLM/
        # OpenAI/OpenRouter all shape this response as {"data": [{"id": ...}]}.
        model_ids = {m.get("id") for m in body.get("data", [])} if isinstance(body, dict) else set()
        if settings.llm_model not in model_ids:
            return ChatStatus(
                available=False,
                provider_type="openai_compatible",
                reason=f"Model '{settings.llm_model}' is not available on the configured LLM provider",
            )

        # Also confirm the MCP server (the chat's only source of read tools)
        # is actually reachable, not just that the LLM endpoint is up.
        try:
            await mcp_client.list_read_tools()
        except Exception as exc:  # noqa: BLE001
            return ChatStatus(available=False, provider_type="openai_compatible", reason=f"MCP server unreachable: {exc}")

        return ChatStatus(available=True, provider_type="openai_compatible", reason=None)

    return ChatStatus(available=False, provider_type=settings.llm_provider_type, reason="Provider type not yet implemented")


@router.post("/sessions", response_model=ChatSessionCreated, status_code=201)
async def create_session(
    body: ChatSessionCreate | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    dashboard_id = body.dashboard_id if body else None
    if dashboard_id is not None:
        dashboard = await db.get(Dashboard, dashboard_id)
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")
    session = ChatSession(dashboard_id=dashboard_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionCreated(id=session.id)


@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.dashboard_id == dashboard_id)
        .options(selectinload(ChatSession.messages))
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    summaries = []
    for s in sessions:
        first_user_message = next(
            (
                m.content.get("content")
                for m in s.messages
                if m.role == "user" and isinstance(m.content.get("content"), str)
            ),
            None,
        )
        summaries.append(ChatSessionSummary(id=s.id, created_at=s.created_at, first_user_message=first_user_message))
    return summaries


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
        try:
            reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(
                db, provider, history, body.message, current_dashboard_id=session.dashboard_id
            )
        except Exception as exc:  # noqa: BLE001
            # run_turn can fail mid-loop (e.g. the provider becomes unreachable
            # after already making write-tool calls that committed via their
            # own service calls). Those writes are already durable; what is
            # NOT yet durable is the user's own message, since run_turn's
            # return value (which normally carries it, as new_messages[0])
            # never arrives. Persist it here so a retried message doesn't
            # look like it silently vanished from the session's history.
            user_turn = {"role": "user", "content": body.message}
            db.add(ChatMessage(session_id=session_id, role=user_turn["role"], content=user_turn))
            await db.commit()
            raise HTTPException(status_code=503, detail=f"LLM provider failed: {exc}") from exc
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            await close()

    for msg in new_messages:
        db.add(ChatMessage(session_id=session_id, role=msg["role"], content=msg))

    if dashboard_id and not session.dashboard_id:
        session.dashboard_id = dashboard_id

    await db.commit()

    return ChatMessageResponse(reply=reply, dashboard_id=session.dashboard_id, actions=actions)
