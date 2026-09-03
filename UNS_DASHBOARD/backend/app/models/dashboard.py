from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Dashboard(TimestampMixin, Base):
    __tablename__ = "dashboards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    charts: Mapped[list[Chart]] = relationship(
        "Chart", back_populates="dashboard", cascade="all, delete-orphan"
    )


class Chart(TimestampMixin, Base):
    __tablename__ = "charts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dashboard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    chart_type: Mapped[str] = mapped_column(String(20), nullable=False)
    data_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    historical_range_type: Mapped[str | None] = mapped_column(String(20))
    historical_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    historical_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    historical_relative_rule: Mapped[str | None] = mapped_column(String(10))
    layout_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layout_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layout_w: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    layout_h: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    color: Mapped[str | None] = mapped_column(String(20))
    config: Mapped[dict | None] = mapped_column(JSONB)

    dashboard: Mapped[Dashboard] = relationship("Dashboard", back_populates="charts")
    signals: Mapped[list[ChartSignal]] = relationship(
        "ChartSignal", back_populates="chart", cascade="all, delete-orphan"
    )


class ChartSignal(TimestampMixin, Base):
    __tablename__ = "chart_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chart_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("charts.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(1024), nullable=False)
    signal_key: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(20))
    min: Mapped[float | None] = mapped_column(Numeric)
    max: Mapped[float | None] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")

    chart: Mapped[Chart] = relationship("Chart", back_populates="signals")
