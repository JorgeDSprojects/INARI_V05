import os

import pytest

from app.database import AsyncSessionLocal, create_tables
from app.models.chat import ChatMessage, ChatSession
from app.models.dashboard import Dashboard

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d dashboard_postgres)"
)


@pytest.mark.asyncio
async def test_chat_session_and_messages_persist_and_relate():
    await create_tables()
    async with AsyncSessionLocal() as db:
        dashboard = Dashboard(name="pytest-chat-model-dashboard")
        db.add(dashboard)
        await db.flush()

        session = ChatSession(dashboard_id=dashboard.id)
        db.add(session)
        await db.flush()

        message = ChatMessage(session_id=session.id, role="user", content={"text": "hola"})
        db.add(message)
        await db.commit()

        await db.refresh(session, attribute_names=["messages"])
        assert len(session.messages) == 1
        assert session.messages[0].content == {"text": "hola"}

        await db.delete(dashboard)
        await db.commit()
