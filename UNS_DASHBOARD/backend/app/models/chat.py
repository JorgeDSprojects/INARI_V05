from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# A process-wide monotonic counter backing ChatMessage's created_at default
# (see below). Plain datetime.now() is not sufficient on its own: verified
# live that several ChatMessage objects constructed back-to-back within one
# request can observe the identical wall-clock tick (clock resolution and/or
# SQLAlchemy evaluating defaults for a batched insert together), which is
# exactly the same tie the DB-side func.now() bug produced. Adding a
# strictly-increasing microsecond offset guarantees distinct, ordered
# timestamps regardless of clock resolution, while still tracking real time.
_created_at_seq = itertools.count()


def _next_created_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(microseconds=next(_created_at_seq))


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dashboard_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("dashboards.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_id_created_at", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Postgres' func.now() is the *transaction* timestamp, so every message
    # written in the same turn (all committed in one transaction by
    # app/routers/chat.py) would otherwise share one identical created_at --
    # both read paths (ChatSession.messages' order_by and the router's
    # history query) sort on created_at alone, so tied timestamps make
    # ordering depend on incidental heap order. The Python-side default
    # runs once per ORM object construction (each ChatMessage(...) call is a
    # separate, later wall-clock instant, even within one DB transaction),
    # giving each row its own distinct, monotonically increasing value.
    # server_default is kept as a DB-level fallback/documentation of intent
    # for any insert that bypasses the ORM's Python-side default.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_next_created_at,
        server_default=func.now(),
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")
