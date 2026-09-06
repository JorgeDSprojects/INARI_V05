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


@pytest.mark.asyncio
async def test_messages_created_in_the_same_transaction_get_strictly_increasing_timestamps():
    """Postgres' func.now() is the *transaction* timestamp, so several
    ChatMessage rows written and committed together (as app/routers/chat.py
    does for a whole turn) would otherwise share one identical created_at --
    and both read paths (ChatSession.messages' order_by and the router's
    history query) sort on created_at alone, silently corrupting replay
    order. ChatMessage.created_at needs a Python-side default so each row
    gets its own distinct, monotonically increasing value even within one
    shared transaction; this test would have caught the original bug (mere
    non-decreasing values would not be enough -- ties are exactly the bug).
    """
    await create_tables()
    async with AsyncSessionLocal() as db:
        session = ChatSession()
        db.add(session)
        await db.flush()

        messages = [
            ChatMessage(session_id=session.id, role="user", content={"text": "one"}),
            ChatMessage(session_id=session.id, role="assistant", content={"text": "two"}),
            ChatMessage(session_id=session.id, role="tool", content={"text": "three"}),
            ChatMessage(session_id=session.id, role="assistant", content={"text": "four"}),
        ]
        for m in messages:
            db.add(m)
        await db.commit()  # all four rows commit in a single transaction

        timestamps = [m.created_at for m in messages]
        assert all(earlier < later for earlier, later in zip(timestamps, timestamps[1:])), timestamps

        await db.delete(session)
        await db.commit()
