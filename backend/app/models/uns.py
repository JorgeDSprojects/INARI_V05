from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Enterprise(TimestampMixin, Base):
    __tablename__ = "enterprises"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    sites: Mapped[list[Site]] = relationship("Site", back_populates="enterprise", cascade="all, delete-orphan")


class Site(TimestampMixin, Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enterprise_id: Mapped[str] = mapped_column(String(36), ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    enterprise: Mapped[Enterprise] = relationship("Enterprise", back_populates="sites")
    areas: Mapped[list[Area]] = relationship("Area", back_populates="site", cascade="all, delete-orphan")


class Area(TimestampMixin, Base):
    __tablename__ = "areas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    site: Mapped[Site] = relationship("Site", back_populates="areas")
    lines: Mapped[list[Line]] = relationship("Line", back_populates="area", cascade="all, delete-orphan")


class Line(TimestampMixin, Base):
    __tablename__ = "lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    area_id: Mapped[str] = mapped_column(String(36), ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    area: Mapped[Area] = relationship("Area", back_populates="lines")
    cells: Mapped[list[Cell]] = relationship("Cell", back_populates="line", cascade="all, delete-orphan")


class Cell(TimestampMixin, Base):
    __tablename__ = "cells"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    line_id: Mapped[str] = mapped_column(String(36), ForeignKey("lines.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    line: Mapped[Line] = relationship("Line", back_populates="cells")
    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="cell", cascade="all, delete-orphan")


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cell_id: Mapped[str] = mapped_column(String(36), ForeignKey("cells.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB)
    uns_topic: Mapped[str | None] = mapped_column(String(1024))
    node_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("node_types.id", ondelete="SET NULL"))
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cell: Mapped[Cell] = relationship("Cell", back_populates="assets")
    node_type: Mapped[object | None] = relationship("NodeType", back_populates="assets")
