from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ChartSignalCreate(BaseModel):
    topic: str
    signal_key: str
    label: str | None = None
    unit: str | None = None
    color: str | None = None
    min: float | None = None
    max: float | None = None
    source: str = "manual"


class ChartSignalRead(_Base, ChartSignalCreate):
    id: str


class ChartCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    chart_type: str
    data_mode: str
    historical_range_type: str | None = None
    historical_from: datetime | None = None
    historical_to: datetime | None = None
    historical_relative_rule: str | None = None
    layout_x: int = 0
    layout_y: int = 0
    layout_w: int = 4
    layout_h: int = 4
    color: str | None = None
    config: dict[str, Any] | None = None
    signals: list[ChartSignalCreate] = []


class ChartUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    chart_type: str | None = None
    data_mode: str | None = None
    historical_range_type: str | None = None
    historical_from: datetime | None = None
    historical_to: datetime | None = None
    historical_relative_rule: str | None = None
    layout_x: int | None = None
    layout_y: int | None = None
    layout_w: int | None = None
    layout_h: int | None = None
    color: str | None = None
    config: dict[str, Any] | None = None
    signals: list[ChartSignalCreate] | None = None


class ChartRead(_Base):
    id: str
    dashboard_id: str
    name: str
    description: str | None
    chart_type: str
    data_mode: str
    historical_range_type: str | None
    historical_from: datetime | None
    historical_to: datetime | None
    historical_relative_rule: str | None
    layout_x: int
    layout_y: int
    layout_w: int
    layout_h: int
    color: str | None
    config: dict[str, Any] | None
    signals: list[ChartSignalRead]


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class DashboardRead(_Base):
    id: str
    name: str
    description: str | None
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DashboardDetailRead(DashboardRead):
    charts: list[ChartRead]
