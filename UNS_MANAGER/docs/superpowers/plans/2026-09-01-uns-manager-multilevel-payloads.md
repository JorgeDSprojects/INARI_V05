# UNS Manager — Multi-Level Payloads + Collapsible Tree + _informative

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `descriptive_payload` and `informative_payload` to all 6 ISA-95 levels (Enterprise → Asset), fix the sidebar tree collapsible behaviour, add a `_informative` tab to NodeWorkspace, and make Enterprise nodes selectable.

**Architecture:** Extend the UNS Manager data model with two JSONB columns (`descriptive_payload`, `informative_payload`) on all six hierarchy tables, add a `last_published_at` timestamp and explicit publish endpoints per level, and generalize the NodeWorkspace component to handle any level's payloads with both a `_descriptive` and a `_informative` tab. The sidebar tree is refactored so each `TreeRow` renders its own children (fixing collapse). Enterprise becomes selectable via a click on its name in the panel header.

**Tech Stack:** FastAPI async + SQLAlchemy 2.x + asyncpg + PostgreSQL JSONB; React + TypeScript + Tailwind CSS; Paho MQTT (via `mqtt_service.publish_descriptive`)

**Spec:** (no separate spec file — authority is this plan and the existing codebase at `master`)

## Global Constraints

- SQLAlchemy 2.x async: all DB operations use `await db.*`
- Pydantic v2: Read schemas use `model_config = ConfigDict(from_attributes=True)`
- **CRITICAL:** Never add `metadata_` to any Pydantic Read schema — it collides with SQLAlchemy's `MetaData()`
- `create_all` only creates tables, never adds columns — use `ALTER TABLE … ADD COLUMN IF NOT EXISTS` in `database.py`
- Topic format: `Enterprise/Site/Area/Line/Cell/Asset/_descriptive` (spaces → underscores, case preserved)
- `_informative` topic = same path, suffix `_informative` instead of `_descriptive`
- Both payloads are retained MQTT messages (QoS 1, retain=True) — `mqtt_service.publish_descriptive(topic, payload)` is a generic retained-JSON publisher; reuse it for `_informative` topics
- Tailwind: approved token families only (surface, ink, border, accent, success, warning, danger, code) — arbitrary hex allowed only in code-editor toolbar areas matching the existing `JsonEditorPanel.tsx` pattern
- No nested `<button>` elements — use `div[role=button]` for any button-inside-button pattern
- URL prefix reference (from router definitions):
  - enterprises: `/enterprises`
  - sites: `/enterprises/{enterprise_id}/sites`
  - areas: `/sites/{site_id}/areas`
  - lines: `/areas/{area_id}/lines`
  - cells: `/lines/{line_id}/cells`
  - assets: `/cells/{cell_id}/assets`

---

## Task 1: Backend — Models + Migration

**Files:**
- Modify: `backend/app/models/uns.py`
- Modify: `backend/app/database.py`

**Interfaces:**
- Produces: `Enterprise.descriptive_payload`, `Enterprise.informative_payload`, `Enterprise.last_published_at` (and same 3 on `Site`, `Area`, `Line`, `Cell`); `Asset.informative_payload` (Asset already has `descriptive_payload` and `last_published_at`)

- [ ] **Step 1: Replace `backend/app/models/uns.py` with the full updated version**

Write the complete file (do not partial-edit — this is the full replacement):

```python
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
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    informative_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sites: Mapped[list[Site]] = relationship("Site", back_populates="enterprise", cascade="all, delete-orphan")


class Site(TimestampMixin, Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enterprise_id: Mapped[str] = mapped_column(String(36), ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    informative_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    enterprise: Mapped[Enterprise] = relationship("Enterprise", back_populates="sites")
    areas: Mapped[list[Area]] = relationship("Area", back_populates="site", cascade="all, delete-orphan")


class Area(TimestampMixin, Base):
    __tablename__ = "areas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    informative_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    site: Mapped[Site] = relationship("Site", back_populates="areas")
    lines: Mapped[list[Line]] = relationship("Line", back_populates="area", cascade="all, delete-orphan")


class Line(TimestampMixin, Base):
    __tablename__ = "lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    area_id: Mapped[str] = mapped_column(String(36), ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    informative_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    area: Mapped[Area] = relationship("Area", back_populates="lines")
    cells: Mapped[list[Cell]] = relationship("Cell", back_populates="line", cascade="all, delete-orphan")


class Cell(TimestampMixin, Base):
    __tablename__ = "cells"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    line_id: Mapped[str] = mapped_column(String(36), ForeignKey("lines.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    informative_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line: Mapped[Line] = relationship("Line", back_populates="cells")
    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="cell", cascade="all, delete-orphan")


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cell_id: Mapped[str] = mapped_column(String(36), ForeignKey("cells.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB)
    informative_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uns_topic: Mapped[str | None] = mapped_column(String(1024))
    node_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("node_types.id", ondelete="SET NULL"))
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cell: Mapped[Cell] = relationship("Cell", back_populates="assets")
    node_type: Mapped[object | None] = relationship("NodeType", back_populates="assets")
```

- [ ] **Step 2: Add migration ALTER TABLE statements in `backend/app/database.py`**

Open `backend/app/database.py`. Find the `create_tables()` function. After the two existing `ALTER TABLE` statements for `assets`, append:

```python
        # Multi-level payload columns (idempotent)
        await conn.execute(text("ALTER TABLE assets ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE enterprises ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE enterprises ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE enterprises ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE sites ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE sites ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE sites ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE lines ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE lines ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE lines ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE cells ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE cells ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE cells ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
```

- [ ] **Step 3: Verify no import errors**

```bash
docker compose run --rm backend python -c "from app.models.uns import Enterprise, Site, Area, Line, Cell, Asset; print('models OK')"
```

Expected: `models OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/uns.py backend/app/database.py
git commit -m "feat: add descriptive_payload, informative_payload, last_published_at to all UNS levels"
```

---

## Task 2: Backend — Schemas + Service + Publish Endpoints

**Files:**
- Modify: `backend/app/schemas/uns.py`
- Modify: `backend/app/services/uns_service.py`
- Modify: `backend/app/routers/enterprises.py`
- Modify: `backend/app/routers/sites.py`
- Modify: `backend/app/routers/areas.py`
- Modify: `backend/app/routers/lines.py`
- Modify: `backend/app/routers/cells.py`

**Interfaces:**
- Consumes: new columns on all models (from Task 1)
- Consumes: `mqtt_service.publish_descriptive(topic, payload)` (existing generic retained-JSON publisher)
- Produces: `EnterpriseRead`, `SiteRead`, `AreaRead`, `LineRead`, `CellRead` — each exposes `descriptive_payload`, `informative_payload`, `last_published_at`
- Produces: `AssetRead`, `AssetUpdate` — add `informative_payload`
- Produces: Tree schemas (`CellTree` → `EnterpriseTree`) — inherit new fields automatically via class inheritance from the Read schemas
- Produces: `build_enterprise_topic(enterprise, suffix)`, `build_site_topic(site, db, suffix)`, `build_area_topic(area, db, suffix)`, `build_line_topic(line, db, suffix)`, `build_cell_topic(cell, db, suffix)` in `uns_service.py`
- Produces: `POST /enterprises/{enterprise_id}/publish`, `POST /enterprises/{enterprise_id}/sites/{site_id}/publish`, `POST /sites/{site_id}/areas/{area_id}/publish`, `POST /areas/{area_id}/lines/{line_id}/publish`, `POST /lines/{line_id}/cells/{cell_id}/publish`

- [ ] **Step 1: Replace `backend/app/schemas/uns.py` with the full updated version**

```python
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
    informative_payload: dict[str, Any] | None
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
```

- [ ] **Step 2: Replace `backend/app/services/uns_service.py` with the full updated version**

Add topic builders for all levels. The `suffix` parameter is `"_descriptive"` or `"_informative"`. The existing `build_uns_topic` gains a `suffix` parameter defaulting to `"_descriptive"` — backward compatible with all current callers.

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uns import Asset, Cell, Line, Area, Site, Enterprise


def _slug(s: str) -> str:
    """Replace spaces with underscores (preserve case)."""
    return s.replace(" ", "_")


async def build_uns_topic(asset: Asset, db: AsyncSession, suffix: str = "_descriptive") -> str:
    cell = await db.get(Cell, asset.cell_id)
    line = await db.get(Line, cell.line_id)
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, line.name, cell.name, asset.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_cell_topic(cell: Cell, db: AsyncSession, suffix: str = "_descriptive") -> str:
    line = await db.get(Line, cell.line_id)
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, line.name, cell.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_line_topic(line: Line, db: AsyncSession, suffix: str = "_descriptive") -> str:
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, line.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_area_topic(area: Area, db: AsyncSession, suffix: str = "_descriptive") -> str:
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_site_topic(site: Site, db: AsyncSession, suffix: str = "_descriptive") -> str:
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, suffix]
    return "/".join(_slug(p) for p in parts)


def build_enterprise_topic(enterprise: Enterprise, suffix: str = "_descriptive") -> str:
    parts = [enterprise.name, suffix]
    return "/".join(_slug(p) for p in parts)
```

- [ ] **Step 3: Add publish endpoint to `backend/app/routers/enterprises.py`**

Open `backend/app/routers/enterprises.py`. Add to the existing imports:

```python
from datetime import datetime, timezone
from app.services.uns_service import build_enterprise_topic
from app.services.mqtt_service import publish_descriptive
```

Add this endpoint after `update_enterprise` and before `delete_enterprise`:

```python
@router.post("/{enterprise_id}/publish", response_model=EnterpriseRead)
async def publish_enterprise(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(build_enterprise_topic(obj, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(build_enterprise_topic(obj, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj
```

- [ ] **Step 4: Add publish endpoint to `backend/app/routers/sites.py`**

Add to existing imports in `sites.py`:

```python
from datetime import datetime, timezone
from app.services.uns_service import build_site_topic
from app.services.mqtt_service import publish_descriptive
```

Add after `update_site`:

```python
@router.post("/{site_id}/publish", response_model=SiteRead)
async def publish_site(enterprise_id: str, site_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_site_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_site_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj
```

- [ ] **Step 5: Add publish endpoint to `backend/app/routers/areas.py`**

Open `areas.py`. Check existing imports; add if missing:

```python
from datetime import datetime, timezone
from app.services.uns_service import build_area_topic
from app.services.mqtt_service import publish_descriptive
```

Add after `update_area`:

```python
@router.post("/{area_id}/publish", response_model=AreaRead)
async def publish_area(site_id: str, area_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_area_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_area_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj
```

Note: You must import `AreaRead` from `app.schemas.uns` if not already imported. Check the existing import line and add `AreaRead` to it.

- [ ] **Step 6: Add publish endpoint to `backend/app/routers/lines.py`**

Add to imports:

```python
from datetime import datetime, timezone
from app.services.uns_service import build_line_topic
from app.services.mqtt_service import publish_descriptive
```

Add after `update_line`:

```python
@router.post("/{line_id}/publish", response_model=LineRead)
async def publish_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_line_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_line_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj
```

Note: Ensure `LineRead` is imported.

- [ ] **Step 7: Add publish endpoint to `backend/app/routers/cells.py`**

Add to imports:

```python
from datetime import datetime, timezone
from app.services.uns_service import build_cell_topic
from app.services.mqtt_service import publish_descriptive
```

Add after `update_cell`:

```python
@router.post("/{cell_id}/publish", response_model=CellRead)
async def publish_cell(line_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_cell_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_cell_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj
```

Note: Ensure `CellRead` is imported.

- [ ] **Step 8: Rebuild backend and verify startup**

```bash
docker compose up backend --build -d
docker compose logs backend --tail=15
```

Expected: `Application startup complete.` — no import errors, no schema validation errors.

- [ ] **Step 9: Quick smoke test**

```bash
# Should return 200 with descriptive_payload, informative_payload, last_published_at fields
curl -s http://localhost:8000/enterprises/ | python -m json.tool | head -20
```

Expected: Response includes `"descriptive_payload": null, "informative_payload": null, "last_published_at": null` for each enterprise.

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/uns.py backend/app/services/uns_service.py \
        backend/app/routers/enterprises.py backend/app/routers/sites.py \
        backend/app/routers/areas.py backend/app/routers/lines.py \
        backend/app/routers/cells.py
git commit -m "feat: payload schemas and publish endpoints for all UNS levels"
```

---

## Task 3: Frontend — Fix Collapsible Tree + Enterprise Selectability

**Files:**
- Modify: `frontend/src/components/TreePanel.tsx`

**Interfaces:**
- Consumes: `onSelect(node: SelectedNode)` — already accepts `level: "enterprise"` per the `HierarchyLevel` type
- Produces: Collapsible tree (clicking the arrow hides/shows children); Enterprise node selectable via click on its name in the header

**Bug being fixed:** `TreeRow` has its own `open` state and toggles the arrow SVG correctly, but children are always rendered because they live in the outer `map` *outside* `TreeRow`. The block `{open && hasChildren && <div>{/* children rendered by parent */}</div>}` at line 83 is dead code — children are never passed inside `TreeRow`.

**Fix:** Add `children?: React.ReactNode` to `RowProps`; render `{open && children}` inside `TreeRow`; restructure the tree map to pass each level's children as nested JSX inside `<TreeRow>`.

- [ ] **Step 1: Add `children` to `RowProps` and update `TreeRow`**

Replace the `RowProps` interface and `TreeRow` function. Key changes:
1. Add `children?: React.ReactNode` to `RowProps`
2. Replace the dead `{open && hasChildren && <div>...</div>}` at the bottom with `{open && children}`

```tsx
interface RowProps {
  label: string;
  level: HierarchyLevel;
  id: string;
  indent: number;
  selected: boolean;
  hasChildren: boolean;
  status?: "synced" | "idle";
  onClick: () => void;
  onAdd?: () => void;
  onCopy?: () => void;
  children?: React.ReactNode;
}

function TreeRow({ label, level, indent, selected, hasChildren, status = "idle", onClick, onAdd, onCopy, children }: RowProps) {
  const [open, setOpen] = useState(true);
  const [hovered, setHovered] = useState(false);

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 h-9 px-2 cursor-pointer rounded mx-1 group ${
          selected ? "bg-accent-soft" : hovered ? "bg-surface-subtle" : ""
        }`}
        style={{ paddingLeft: `${8 + indent * 16}px` }}
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <button
          onClick={e => { e.stopPropagation(); setOpen(!open); }}
          className="w-3.5 h-3.5 flex items-center justify-center text-ink-muted shrink-0"
        >
          {hasChildren ? (
            <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
              {open
                ? <path d="M0 2l4 4 4-4H0z"/>
                : <path d="M2 0l4 4-4 4V0z"/>
              }
            </svg>
          ) : (
            <span className="w-1 h-1 rounded-full bg-ink-muted/40 inline-block" />
          )}
        </button>

        <span className={`w-3.5 h-3.5 shrink-0 ${selected ? "text-accent" : "text-ink-secondary"}`}>
          {LEVEL_ICON[level]}
        </span>

        <span className={`flex-1 text-sm truncate ${selected ? "text-ink font-medium" : "text-ink-secondary"}`}>
          {label}
        </span>

        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${status === "synced" ? "bg-success" : "bg-ink-muted/40"}`} />

        {onAdd && (hovered || selected) && (
          <button
            onClick={e => { e.stopPropagation(); onAdd(); }}
            className="w-5 h-5 flex items-center justify-center text-ink-muted hover:text-ink rounded text-xs shrink-0"
            title="Add child"
          >+</button>
        )}
        {onCopy && (hovered || selected) && (
          <button
            onClick={e => { e.stopPropagation(); onCopy(); }}
            className="w-5 h-5 flex items-center justify-center text-ink-muted hover:text-ink rounded text-xs shrink-0"
            title="Copy/Move"
          >⧉</button>
        )}
      </div>
      {open && children}
    </div>
  );
}
```

- [ ] **Step 2: Restructure the tree map to nest children inside `<TreeRow>`**

Find the `{/* Tree */}` section (the `<div className="flex-1 overflow-y-auto py-1">` block). Replace the entire inner content with the nested structure below. Each level's children are passed as JSX children of the parent `<TreeRow>`:

```tsx
{/* Tree */}
<div className="flex-1 overflow-y-auto py-1">
  {enterprise.sites
    .filter(s => !search || s.name.toLowerCase().includes(search.toLowerCase()))
    .map(site => (
      <TreeRow
        key={site.id}
        label={site.name} level="site" id={site.id} indent={0}
        hasChildren={site.areas.length > 0} status="synced"
        selected={selected?.level === "site" && selected.id === site.id}
        onClick={() => onSelect({ level: "site", id: site.id, parentIds: { enterprise_id: enterprise.id } })}
        onAdd={() => setAddingChild({ level: "site", parentId: site.id })}
        onCopy={() => setCopyMoveNode({ id: site.id, level: "site", name: site.name })}
      >
        {site.areas.map(area => (
          <TreeRow
            key={area.id}
            label={area.name} level="area" id={area.id} indent={1}
            hasChildren={area.lines.length > 0}
            selected={selected?.level === "area" && selected.id === area.id}
            onClick={() => onSelect({ level: "area", id: area.id, parentIds: { site_id: site.id } })}
            onAdd={() => setAddingChild({ level: "area", parentId: area.id })}
            onCopy={() => setCopyMoveNode({ id: area.id, level: "area", name: area.name })}
          >
            {area.lines.map(line => (
              <TreeRow
                key={line.id}
                label={line.name} level="line" id={line.id} indent={2}
                hasChildren={line.cells.length > 0}
                selected={selected?.level === "line" && selected.id === line.id}
                onClick={() => onSelect({ level: "line", id: line.id, parentIds: { area_id: area.id } })}
                onAdd={() => setAddingChild({ level: "line", parentId: line.id })}
                onCopy={() => setCopyMoveNode({ id: line.id, level: "line", name: line.name })}
              >
                {line.cells.map(cell => (
                  <TreeRow
                    key={cell.id}
                    label={cell.name} level="cell" id={cell.id} indent={3}
                    hasChildren={cell.assets.length > 0}
                    selected={selected?.level === "cell" && selected.id === cell.id}
                    onClick={() => onSelect({ level: "cell", id: cell.id, parentIds: { line_id: line.id } })}
                    onAdd={() => setAssetModalCellId(cell.id)}
                    onCopy={() => setCopyMoveNode({ id: cell.id, level: "cell", name: cell.name })}
                  >
                    {cell.assets.map(asset => (
                      <TreeRow
                        key={asset.id}
                        label={asset.name} level="asset" id={asset.id} indent={4}
                        hasChildren={false}
                        status={asset.descriptive_payload && Object.keys(asset.descriptive_payload).length > 0 ? "synced" : "idle"}
                        selected={selected?.level === "asset" && selected.id === asset.id}
                        onClick={() => onSelect({ level: "asset", id: asset.id, parentIds: { cell_id: cell.id } })}
                      />
                    ))}
                  </TreeRow>
                ))}
              </TreeRow>
            ))}
          </TreeRow>
        ))}
      </TreeRow>
    ))}
</div>
```

- [ ] **Step 3: Make Enterprise selectable in the panel header**

In the panel header section, find the enterprise name div:

```tsx
<div className="text-sm font-semibold text-ink truncate">{enterprise.name}</div>
```

Replace with:

```tsx
<div
  className={`text-sm font-semibold truncate cursor-pointer hover:text-accent transition-colors ${
    selected?.level === "enterprise" && selected.id === enterprise.id ? "text-accent" : "text-ink"
  }`}
  onClick={() => onSelect({ level: "enterprise", id: enterprise.id, parentIds: {} })}
>
  {enterprise.name}
</div>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TreePanel.tsx
git commit -m "fix: collapsible tree via children prop; make Enterprise selectable in header"
```

---

## Task 4: Frontend — TypeScript Types + API Client

**Files:**
- Modify: `frontend/src/types/uns.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: new backend fields and endpoints from Tasks 1 + 2
- Produces: `Enterprise`, `Site`, `Area`, `Line`, `Cell`, `Asset` TS interfaces — all include `descriptive_payload`, `informative_payload`, `last_published_at`; Tree interfaces inherit via extension
- Produces: `api.enterprises.publish(id)`, `api.sites.publish(enterpriseId, siteId)`, `api.areas.publish(siteId, areaId)`, `api.lines.publish(areaId, lineId)`, `api.cells.publish(lineId, cellId)`
- Produces: `api.assets.update` body type includes `informative_payload`

- [ ] **Step 1: Replace the six base interfaces in `frontend/src/types/uns.ts`**

Replace only the Enterprise, Site, Area, Line, Cell, Asset interfaces. Keep everything else (CellTree through EnterpriseTree, HierarchyLevel, SelectedNode, Broker, BrokerStatus, BrokerTestResult, NodeType, ValidationResult, DataBranch, SyncStatus) exactly as-is.

```typescript
export interface Enterprise {
  id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Site {
  id: string;
  enterprise_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Area {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Line {
  id: string;
  area_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Cell {
  id: string;
  line_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  cell_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
  uns_topic: string | null;
  node_type_id: string | null;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Update `frontend/src/api/client.ts`**

Add a shared `PayloadFields` helper type at the top (after imports), add `publish` to each level's client, and widen the `update` body types to include payload fields.

Write the complete file — full replacement:

```typescript
import axios from "axios";
import type { Asset, Area, Broker, BrokerStatus, BrokerTestResult, Cell, DataBranch, Enterprise, EnterpriseTree, Line, NodeType, Site, SyncStatus, ValidationResult } from "../types/uns";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const http = axios.create({ baseURL: BASE });

type PayloadFields = {
  descriptive_payload?: Record<string, unknown> | null;
  informative_payload?: Record<string, unknown> | null;
};

export const api = {
  tree: {
    get: () => http.get<EnterpriseTree[]>("/tree/").then((r) => r.data),
    copy: (body: { source_id: string; source_level: string; target_parent_id: string }) =>
      http.post<{ new_root_id: string; node_count: number }>("/tree/copy", body).then((r) => r.data),
    move: (body: { source_id: string; source_level: string; target_parent_id: string }) =>
      http.post<{ moved_root_id: string; node_count: number }>("/tree/move", body).then((r) => r.data),
    publishSubtree: (body: { root_id: string; root_level: string }) =>
      http.post<{ published: number; failed: number }>("/tree/publish-subtree", body).then((r) => r.data),
  },
  enterprises: {
    list: () => http.get<Enterprise[]>("/enterprises/").then((r) => r.data),
    get: (id: string) => http.get<Enterprise>(`/enterprises/${id}`).then((r) => r.data),
    create: (body: { name: string; description?: string; metadata?: Record<string, unknown> }) =>
      http.post<Enterprise>("/enterprises/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string; metadata: Record<string, unknown> } & PayloadFields>) =>
      http.patch<Enterprise>(`/enterprises/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/enterprises/${id}`),
    publish: (id: string) =>
      http.post<Enterprise>(`/enterprises/${id}/publish`).then((r) => r.data),
  },
  sites: {
    list: (enterpriseId: string) =>
      http.get<Site[]>(`/enterprises/${enterpriseId}/sites/`).then((r) => r.data),
    create: (enterpriseId: string, body: { name: string; description?: string }) =>
      http.post<Site>(`/enterprises/${enterpriseId}/sites/`, body).then((r) => r.data),
    update: (enterpriseId: string, siteId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Site>(`/enterprises/${enterpriseId}/sites/${siteId}`, body).then((r) => r.data),
    delete: (enterpriseId: string, siteId: string) =>
      http.delete(`/enterprises/${enterpriseId}/sites/${siteId}`),
    publish: (enterpriseId: string, siteId: string) =>
      http.post<Site>(`/enterprises/${enterpriseId}/sites/${siteId}/publish`).then((r) => r.data),
  },
  areas: {
    list: (siteId: string) => http.get<Area[]>(`/sites/${siteId}/areas/`).then((r) => r.data),
    create: (siteId: string, body: { name: string; description?: string }) =>
      http.post<Area>(`/sites/${siteId}/areas/`, body).then((r) => r.data),
    update: (siteId: string, areaId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Area>(`/sites/${siteId}/areas/${areaId}`, body).then((r) => r.data),
    delete: (siteId: string, areaId: string) => http.delete(`/sites/${siteId}/areas/${areaId}`),
    publish: (siteId: string, areaId: string) =>
      http.post<Area>(`/sites/${siteId}/areas/${areaId}/publish`).then((r) => r.data),
  },
  lines: {
    list: (areaId: string) => http.get<Line[]>(`/areas/${areaId}/lines/`).then((r) => r.data),
    create: (areaId: string, body: { name: string; description?: string }) =>
      http.post<Line>(`/areas/${areaId}/lines/`, body).then((r) => r.data),
    update: (areaId: string, lineId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Line>(`/areas/${areaId}/lines/${lineId}`, body).then((r) => r.data),
    delete: (areaId: string, lineId: string) => http.delete(`/areas/${areaId}/lines/${lineId}`),
    publish: (areaId: string, lineId: string) =>
      http.post<Line>(`/areas/${areaId}/lines/${lineId}/publish`).then((r) => r.data),
  },
  cells: {
    list: (lineId: string) => http.get<Cell[]>(`/lines/${lineId}/cells/`).then((r) => r.data),
    create: (lineId: string, body: { name: string; description?: string }) =>
      http.post<Cell>(`/lines/${lineId}/cells/`, body).then((r) => r.data),
    update: (lineId: string, cellId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Cell>(`/lines/${lineId}/cells/${cellId}`, body).then((r) => r.data),
    delete: (lineId: string, cellId: string) => http.delete(`/lines/${lineId}/cells/${cellId}`),
    publish: (lineId: string, cellId: string) =>
      http.post<Cell>(`/lines/${lineId}/cells/${cellId}/publish`).then((r) => r.data),
  },
  assets: {
    list: (cellId: string) => http.get<Asset[]>(`/cells/${cellId}/assets/`).then((r) => r.data),
    create: (cellId: string, body: { name: string; description?: string; descriptive_payload?: Record<string, unknown>; node_type_id?: string }) =>
      http.post<Asset>(`/cells/${cellId}/assets/`, body).then((r) => r.data),
    update: (cellId: string, assetId: string, body: Partial<{ name: string; description: string } & PayloadFields>) =>
      http.patch<Asset>(`/cells/${cellId}/assets/${assetId}`, body).then((r) => r.data),
    delete: (cellId: string, assetId: string) => http.delete(`/cells/${cellId}/assets/${assetId}`),
    publish: (cellId: string, assetId: string) =>
      http.post<Asset>(`/cells/${cellId}/assets/${assetId}/publish`).then((r) => r.data),
  },
  brokers: {
    list: () => http.get<Broker[]>("/brokers/").then((r) => r.data),
    create: (body: { label: string; host: string; port: number; api_port: number; username?: string; password?: string; use_tls?: boolean }) =>
      http.post<Broker>("/brokers/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ label: string; host: string; port: number; api_port: number; username: string; password: string; use_tls: boolean }>) =>
      http.put<Broker>(`/brokers/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/brokers/${id}`),
    status: (id: string) => http.get<BrokerStatus>(`/brokers/${id}/status`).then((r) => r.data),
    test: (id: string) => http.post<BrokerTestResult>(`/brokers/${id}/test`).then((r) => r.data),
  },
  nodeTypes: {
    list: () => http.get<NodeType[]>("/node-types/").then((r) => r.data),
    create: (body: { name: string; description?: string; json_schema: Record<string, unknown> }) =>
      http.post<NodeType>("/node-types/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string; json_schema: Record<string, unknown> }>) =>
      http.put<NodeType>(`/node-types/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/node-types/${id}`),
    validate: (id: string, payload: Record<string, unknown>) =>
      http.post<ValidationResult>(`/node-types/${id}/validate`, { payload }).then((r) => r.data),
  },
  branches: {
    list: (cellId: string, assetId: string) =>
      http.get<DataBranch[]>(`/cells/${cellId}/assets/${assetId}/branches`).then((r) => r.data),
  },
  syncStatus: {
    get: (cellId: string, assetId: string) =>
      http.get<SyncStatus>(`/cells/${cellId}/assets/${assetId}/sync-status`).then((r) => r.data),
  },
};
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && node node_modules/typescript/bin/tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/uns.ts frontend/src/api/client.ts
git commit -m "feat: add descriptive_payload, informative_payload, publish to all TS types and API client"
```

---

## Task 5: Frontend — NodeWorkspace Generalization + _informative Tab

**Files:**
- Modify: `frontend/src/components/NodeWorkspace.tsx`

**Interfaces:**
- Consumes: `api.enterprises/sites/areas/lines/cells/assets .update` and `.publish` (from Task 4)
- Consumes: `Enterprise`, `Site`, `Area`, `Line`, `Cell`, `Asset` — all now have `descriptive_payload`, `informative_payload` (from Task 4)
- Consumes: `EnterpriseTree` tree prop now carries payload fields on all nodes (from Task 2 + Task 4)
- Consumes: `JsonEditorPanel` props: `{ payload, onChange, onValidChange, unsTopic, asset, readOnly, onEdit, lines? }` (existing, unchanged)
- Produces: `_descriptive` tab works for all 6 levels (removes `selected.level === "asset"` guard); `_informative` tab (new, same `JsonEditorPanel`); Enterprise workspace visible; payload auto-loaded from tree for non-asset levels

**Context — current state of NodeWorkspace:**
- `payload` state = descriptive payload; `editMode` = edit state; `jsonValid` = JSON validity
- `asset` state = full `Asset` object, only set when `selected.level === "asset"`
- `tab` type = `"definition" | "_descriptive" | "branches" | "_operational" | "_analytical"`
- `handleSave` and `handlePublish` guard with `if (!asset ...) return` — must be replaced
- `useEffect([selected])` loads asset from API; for non-asset levels, falls through to `setAsset(null)`
- `buildTopic(enterprise, selected, name)` builds a display topic string ending in `/_descriptive`

- [ ] **Step 1: Add `_informative` to the `Tab` type**

```tsx
type Tab = "definition" | "_descriptive" | "_informative" | "branches" | "_operational" | "_analytical";
```

- [ ] **Step 2: Add informative payload state**

Inside the component, alongside the existing state, add:

```tsx
const [infoPayload, setInfoPayload] = useState<Record<string, unknown>>({});
const [infoJsonValid, setInfoJsonValid] = useState(true);
const [infoEditMode, setInfoEditMode] = useState(false);
```

- [ ] **Step 3: Add `findNodeInTree` helper**

Add this function outside the component (alongside the existing `getNodeName`, `getNodePath`, `buildTopic` helpers at the bottom of the file):

```tsx
type NodePayloads = {
  descriptive_payload: Record<string, unknown> | null;
  informative_payload: Record<string, unknown> | null;
};

function findNodeInTree(enterprise: EnterpriseTree, selected: SelectedNode): NodePayloads | null {
  if (selected.level === "enterprise" && enterprise.id === selected.id) return enterprise;
  for (const site of enterprise.sites) {
    if (selected.level === "site" && site.id === selected.id) return site;
    for (const area of site.areas) {
      if (selected.level === "area" && area.id === selected.id) return area;
      for (const line of area.lines) {
        if (selected.level === "line" && line.id === selected.id) return line;
        for (const cell of line.cells) {
          if (selected.level === "cell" && cell.id === selected.id) return cell;
          for (const asset of cell.assets) {
            if (selected.level === "asset" && asset.id === selected.id) return asset;
          }
        }
      }
    }
  }
  return null;
}
```

- [ ] **Step 4: Generalize the `useEffect` that loads node data**

Replace the existing `useEffect` (the one with `[selected]` dependency) with a generalized version. Add `enterprise` to the dependency array so non-asset nodes refresh when the tree reloads after a save.

```tsx
useEffect(() => {
  // Reset all payload state on node change
  setPayload({});
  setInfoPayload({});
  setEditMode(false);
  setInfoEditMode(false);
  setAsset(null);
  setSyncStatus(null);
  setSyncError(null);
  setBranches([]);

  if (!selected) return;

  // Load payloads from the already-loaded tree (works for all levels)
  const node = findNodeInTree(enterprise, selected);
  if (node) {
    setPayload(node.descriptive_payload ?? {});
    setInfoPayload(node.informative_payload ?? {});
  }

  // For assets: also fetch the full Asset object from the API
  // (needed for uns_topic, node_type_id, and sync status)
  if (selected.level === "asset" && selected.parentIds.cell_id) {
    api.assets.list(selected.parentIds.cell_id).then(list => {
      const found = list.find(a => a.id === selected.id);
      if (found) {
        setAsset(found);
        setPayload(found.descriptive_payload ?? {});
        setInfoPayload(found.informative_payload ?? {});
        api.syncStatus.get(selected.parentIds.cell_id, found.id)
          .then(setSyncStatus)
          .catch(() => setSyncStatus(null));
      }
    });
  }
}, [selected, enterprise]);
```

- [ ] **Step 5: Replace `handleSave` and `handlePublish` with level-aware versions**

```tsx
const handleSave = async () => {
  if (!selected) return;
  setSaving(true);
  try {
    const isInfo = tab === "_informative";
    const body = isInfo
      ? { informative_payload: infoPayload }
      : { descriptive_payload: payload };
    switch (selected.level) {
      case "enterprise":
        await api.enterprises.update(selected.id, body); break;
      case "site":
        await api.sites.update(selected.parentIds.enterprise_id, selected.id, body); break;
      case "area":
        await api.areas.update(selected.parentIds.site_id, selected.id, body); break;
      case "line":
        await api.lines.update(selected.parentIds.area_id, selected.id, body); break;
      case "cell":
        await api.cells.update(selected.parentIds.line_id, selected.id, body); break;
      case "asset":
        await api.assets.update(selected.parentIds.cell_id, selected.id, body); break;
    }
    if (isInfo) setInfoEditMode(false); else setEditMode(false);
    onRefresh();
  } finally { setSaving(false); }
};

const handlePublish = async () => {
  if (!selected) return;
  setSaving(true);
  try {
    const isInfo = tab === "_informative";
    const body = isInfo
      ? { informative_payload: infoPayload }
      : { descriptive_payload: payload };
    switch (selected.level) {
      case "enterprise":
        await api.enterprises.update(selected.id, body);
        await api.enterprises.publish(selected.id); break;
      case "site":
        await api.sites.update(selected.parentIds.enterprise_id, selected.id, body);
        await api.sites.publish(selected.parentIds.enterprise_id, selected.id); break;
      case "area":
        await api.areas.update(selected.parentIds.site_id, selected.id, body);
        await api.areas.publish(selected.parentIds.site_id, selected.id); break;
      case "line":
        await api.lines.update(selected.parentIds.area_id, selected.id, body);
        await api.lines.publish(selected.parentIds.area_id, selected.id); break;
      case "cell":
        await api.cells.update(selected.parentIds.line_id, selected.id, body);
        await api.cells.publish(selected.parentIds.line_id, selected.id); break;
      case "asset": {
        await api.assets.update(selected.parentIds.cell_id, selected.id, body);
        await api.assets.publish(selected.parentIds.cell_id, selected.id);
        const s = await api.syncStatus.get(selected.parentIds.cell_id, selected.id);
        setSyncStatus(s);
        break;
      }
    }
    setPublished(true);
    setTimeout(() => setPublished(false), 3000);
    onRefresh();
  } finally { setSaving(false); }
};
```

- [ ] **Step 6: Update the TABS definition**

```tsx
const TABS: { id: Tab; label: string; dot?: "success" | "muted" }[] = [
  { id: "definition", label: "Definition" },
  { id: "_descriptive", label: "_descriptive", dot: Object.keys(payload).length > 0 ? "success" : "muted" },
  { id: "_informative", label: "_informative", dot: Object.keys(infoPayload).length > 0 ? "success" : "muted" },
  { id: "branches", label: `Data branches · ${branches.length}`, dot: branches.length > 0 ? "success" : "muted" },
  { id: "_operational", label: "_operational", dot: "muted" },
  { id: "_analytical", label: "_analytical", dot: "muted" },
];
```

- [ ] **Step 7: Update the meta bar to handle both payload tabs**

Replace the existing meta bar block (currently guarded by `tab === "_descriptive"`) with a version that covers both tabs:

```tsx
{/* Meta bar — _descriptive and _informative */}
{(tab === "_descriptive" || tab === "_informative") && (
  <div className="flex items-center justify-between px-6 py-2.5 bg-surface-subtle border-b border-border-subtle">
    <div className="flex items-center gap-4">
      <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-accent-soft text-accent text-[10px] font-medium">
        ◈ RETAINED
      </span>
      <span className="text-ink-secondary text-xs">application/json</span>
      <span className="text-ink-muted text-[10px]">
        {new TextEncoder().encode(
          JSON.stringify(tab === "_informative" ? infoPayload : payload, null, 2)
        ).length} BYTES
      </span>
    </div>
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-1">
        {(tab === "_informative" ? infoJsonValid : jsonValid) ? (
          <><span className="text-success text-xs">✓</span><span className="text-success text-xs">Valid JSON</span></>
        ) : (
          <><span className="text-danger text-xs">✗</span><span className="text-danger text-xs">Invalid JSON</span></>
        )}
      </div>
      <span className="text-ink-muted text-[10px]">POSTGRES REV {asset ? "active" : "–"}</span>
      {(tab === "_descriptive" ? editMode : infoEditMode) && (
        <div className="flex items-center gap-2">
          <button
            onClick={handleSave}
            disabled={saving || !(tab === "_informative" ? infoJsonValid : jsonValid)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-ink text-white text-xs rounded disabled:opacity-50"
          >
            SAVE
          </button>
          <button
            onClick={handlePublish}
            disabled={saving || !(tab === "_informative" ? infoJsonValid : jsonValid)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent text-white text-xs rounded disabled:opacity-50"
          >
            {published ? "PUBLISHED ✓" : "SAVE & PUBLISH"}
          </button>
        </div>
      )}
    </div>
  </div>
)}
```

- [ ] **Step 8: Replace the work area conditional rendering**

Find the `{/* Work area */}` block. The current top of the conditional is:
```tsx
{tab === "_descriptive" && selected.level === "asset" ? (
```

Replace the entire conditional in the work area with the following. The `_descriptive` case now drops the `selected.level === "asset"` guard. A new `_informative` case is inserted. The branches panel, definition panel, and fallback remain exactly as-is:

```tsx
{/* Work area */}
<div className="flex flex-1 overflow-hidden">
  {tab === "_descriptive" ? (
    <JsonEditorPanel
      payload={payload}
      onChange={setPayload}
      onValidChange={setJsonValid}
      unsTopic={asset?.uns_topic ?? buildTopic(enterprise, selected, nodeName)}
      asset={asset}
      readOnly={!editMode}
      onEdit={() => setEditMode(true)}
      lines={JSON.stringify(payload, null, 2).split("\n").length}
    />
  ) : tab === "_informative" ? (
    <JsonEditorPanel
      payload={infoPayload}
      onChange={setInfoPayload}
      onValidChange={setInfoJsonValid}
      unsTopic={(asset?.uns_topic ?? buildTopic(enterprise, selected, nodeName)).replace("_descriptive", "_informative")}
      asset={null}
      readOnly={!infoEditMode}
      onEdit={() => setInfoEditMode(true)}
      lines={JSON.stringify(infoPayload, null, 2).split("\n").length}
    />
  ) : tab === "definition" ? (
    <DefinitionPanel enterprise={enterprise} selected={selected} />
  ) : tab === "branches" ? (
    /* Keep the entire branches panel block exactly as it exists — do not modify */
    <BRANCHES_PANEL_UNCHANGED />
  ) : (
    <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
      {`${tab} payload comes from external services at runtime.`}
    </div>
  )}
</div>
```

**Note:** The `<BRANCHES_PANEL_UNCHANGED />` above is a placeholder reminder — copy the existing branches `<div className="flex-1 flex flex-col overflow-hidden">…</div>` block verbatim from the current file. Do not modify it.

- [ ] **Step 9: TypeScript check**

```bash
cd frontend && node node_modules/typescript/bin/tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/NodeWorkspace.tsx
git commit -m "feat: _descriptive and _informative tabs for all levels; workspace generalized"
```

---

## Self-Review

**Spec coverage:**
- All 6 levels have `descriptive_payload` and `informative_payload` → Tasks 1, 2, 4, 5 ✓
- Publish endpoints for all levels → Task 2 ✓
- `_informative` tab in NodeWorkspace → Task 5 ✓
- Collapsible tree → Task 3 ✓
- Enterprise node selectable → Task 3 ✓

**Type consistency:**
- `build_site_topic(site, db, suffix)` defined T2, called in T2 sites.py ✓
- `api.sites.publish(entId, siteId)` → URL `/enterprises/${entId}/sites/${siteId}/publish` matches router prefix `/enterprises/{enterprise_id}/sites` + endpoint `/{site_id}/publish` ✓
- `infoPayload` state used in T5 for `_informative` tab; `findNodeInTree` returns `NodePayloads` with `informative_payload` ✓
- `EnterpriseTree` inherits `descriptive_payload`/`informative_payload` from `EnterpriseRead` (Pydantic) and from `Enterprise` interface (TS) — consumed by `findNodeInTree` ✓
- `handlePublish` for asset case calls `api.syncStatus.get` and `setSyncStatus` exactly as original ✓
- `useEffect([selected, enterprise])` — adding `enterprise` to deps is required so non-asset payload displays refresh when `onRefresh()` re-fetches the tree ✓

**Ordering:** T1 → T2 → T3 → T4 → T5. T3 is independent (pure frontend, no new API calls). T4 needs T1+T2 field names. T5 needs T4.

**No placeholders:** All code blocks are complete implementations.
