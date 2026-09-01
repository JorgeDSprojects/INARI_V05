from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.uns import TimestampMixin, _uuid


class NodeType(TimestampMixin, Base):
    __tablename__ = "node_types"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    json_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    assets: Mapped[list] = relationship("Asset", back_populates="node_type")
