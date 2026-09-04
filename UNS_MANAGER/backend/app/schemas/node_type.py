from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NodeTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    json_schema: dict[str, Any] = Field(default_factory=dict)


class NodeTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    json_schema: dict[str, Any] | None = None


class NodeTypeRead(_Base):
    id: str
    name: str
    description: str | None
    json_schema: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = []
