from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Enterprise ───────────────────────────────────────────────────────────────

class EnterpriseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    model_config = ConfigDict(populate_by_name=True)


class EnterpriseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    descriptive_payload: dict[str, Any] | None = None
    informative_payload: dict[str, Any] | None = None
    model_config = ConfigDict(populate_by_name=True)


class EnterpriseRead(_Base):
    id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    informative_payload: dict[str, Any] | None
    last_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Site ─────────────────────────────────────────────────────────────────────

class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    model_config = ConfigDict(populate_by_name=True)


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    descriptive_payload: dict[str, Any] | None = None
    informative_payload: dict[str, Any] | None = None
    model_config = ConfigDict(populate_by_name=True)


class SiteRead(_Base):
    id: str
    enterprise_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    informative_payload: dict[str, Any] | None
    last_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Area ─────────────────────────────────────────────────────────────────────

class AreaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    model_config = ConfigDict(populate_by_name=True)


class AreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    descriptive_payload: dict[str, Any] | None = None
    informative_payload: dict[str, Any] | None = None
    model_config = ConfigDict(populate_by_name=True)


class AreaRead(_Base):
    id: str
    site_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    informative_payload: dict[str, Any] | None
    last_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Line ─────────────────────────────────────────────────────────────────────

class LineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    model_config = ConfigDict(populate_by_name=True)


class LineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    descriptive_payload: dict[str, Any] | None = None
    informative_payload: dict[str, Any] | None = None
    model_config = ConfigDict(populate_by_name=True)


class LineRead(_Base):
    id: str
    area_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    informative_payload: dict[str, Any] | None
    last_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Cell ─────────────────────────────────────────────────────────────────────

class CellCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    model_config = ConfigDict(populate_by_name=True)


class CellUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    descriptive_payload: dict[str, Any] | None = None
    informative_payload: dict[str, Any] | None = None
    model_config = ConfigDict(populate_by_name=True)


class CellRead(_Base):
    id: str
    line_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    informative_payload: dict[str, Any] | None
    last_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Asset ────────────────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    descriptive_payload: dict[str, Any] | None = None
    node_type_id: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    descriptive_payload: dict[str, Any] | None = None
    informative_payload: dict[str, Any] | None = None
    node_type_id: str | None = None


class AssetRead(_Base):
    id: str
    cell_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    uns_topic: str | None
    node_type_id: str | None
    last_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ─── Tree ─────────────────────────────────────────────────────────────────────

class CellTree(CellRead):
    assets: list[AssetRead] = []


class LineTree(LineRead):
    cells: list[CellTree] = []


class AreaTree(AreaRead):
    lines: list[LineTree] = []


class SiteTree(SiteRead):
    areas: list[AreaTree] = []


class EnterpriseTree(EnterpriseRead):
    sites: list[SiteTree] = []
