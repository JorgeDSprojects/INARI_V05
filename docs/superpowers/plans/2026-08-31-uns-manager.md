# UNS Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack UNS Manager that models ISA-95 hierarchy (Enterprise→Site→Area→Line→Cell→Asset) in PostgreSQL and publishes `_descriptive` payloads to EMQX via MQTT.

**Architecture:** FastAPI backend exposes CRUD APIs for the 6 ISA-95 hierarchy levels and uses paho-mqtt to publish retained messages to EMQX at `Enterprise/Site/Area/Line/Cell/Asset/_descriptive`. A React/TypeScript frontend renders the hierarchy as a tree and provides a JSON editor for descriptive payloads.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x (async), asyncpg, paho-mqtt, PostgreSQL 16, EMQX 5.x, React 18, TypeScript, Vite, Tailwind CSS 3, Docker Compose.

---

## File Structure

```
INARI_V04/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # FastAPI app, lifespan, CORS
│       ├── config.py          # Settings from env
│       ├── database.py        # Async SQLAlchemy engine + session
│       ├── models/
│       │   ├── __init__.py
│       │   └── uns.py         # 6 ORM models (Enterprise…Asset)
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── uns.py         # Pydantic v2 request/response schemas
│       ├── services/
│       │   ├── __init__.py
│       │   ├── uns_service.py  # UNS topic path builder
│       │   └── mqtt_service.py # paho-mqtt publish helper
│       └── routers/
│           ├── __init__.py
│           ├── enterprises.py
│           ├── sites.py
│           ├── areas.py
│           ├── lines.py
│           ├── cells.py
│           └── assets.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── types/
│       │   └── uns.ts         # TS interfaces matching API
│       ├── api/
│       │   └── client.ts      # axios-based API client
│       ├── components/
│       │   ├── UnsTree.tsx    # Recursive hierarchy tree
│       │   ├── NodeForm.tsx   # Create/edit form for any level
│       │   ├── AssetDetail.tsx # Asset detail panel
│       │   └── JsonEditor.tsx  # Textarea-based JSON editor
│       └── hooks/
│           └── useUnsTree.ts  # Data fetching + mutation hooks
```

---

## Task 1: Infrastructure — docker-compose.yml + .env.example

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create .env.example**

```bash
cat > "G:/00_data/00_Formacion/INARI_V04/.env.example" << 'EOF'
# PostgreSQL
POSTGRES_USER=unsadmin
POSTGRES_PASSWORD=unspassword
POSTGRES_DB=unsdb
DATABASE_URL=postgresql+asyncpg://unsadmin:unspassword@postgres:5432/unsdb

# EMQX
EMQX_HOST=emqx
EMQX_PORT=1883
EMQX_API_HOST=emqx
EMQX_API_PORT=18083
EMQX_API_USER=admin
EMQX_API_PASSWORD=public

# Backend
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Frontend
VITE_API_BASE_URL=http://localhost:8000
EOF
```

- [ ] **Step 2: Create docker-compose.yml**

File content for `docker-compose.yml`:

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    container_name: uns_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-unsadmin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-unspassword}
      POSTGRES_DB: ${POSTGRES_DB:-unsdb}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-unsadmin} -d ${POSTGRES_DB:-unsdb}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - uns_net

  emqx:
    image: emqx:5.8
    container_name: uns_emqx
    environment:
      EMQX_NODE__NAME: emqx@127.0.0.1
      EMQX_DASHBOARD__DEFAULT_PASSWORD: public
    ports:
      - "1883:1883"    # MQTT
      - "8083:8083"    # MQTT/WS
      - "18083:18083"  # Dashboard API
    volumes:
      - emqx_data:/opt/emqx/data
      - emqx_log:/opt/emqx/log
    healthcheck:
      test: ["CMD", "/opt/emqx/bin/emqx", "ctl", "status"]
      interval: 15s
      timeout: 10s
      retries: 10
    networks:
      - uns_net

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: uns_backend
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql+asyncpg://unsadmin:unspassword@postgres:5432/unsdb}
      EMQX_HOST: ${EMQX_HOST:-emqx}
      EMQX_PORT: ${EMQX_PORT:-1883}
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      emqx:
        condition: service_healthy
    networks:
      - uns_net
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:8000}
    container_name: uns_frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
    networks:
      - uns_net
    restart: unless-stopped

volumes:
  postgres_data:
  emqx_data:
  emqx_log:

networks:
  uns_net:
    driver: bridge
```

- [ ] **Step 3: Copy .env.example to .env**

```bash
cp .env.example .env
```

---

## Task 2: Backend — Dockerfile + requirements.txt

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic==2.10.3
pydantic-settings==2.7.0
paho-mqtt==2.1.0
httpx==0.28.1
python-multipart==0.0.20
```

- [ ] **Step 2: Create backend/Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Task 3: Backend — config.py + database.py

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`

- [ ] **Step 1: Create backend/app/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://unsadmin:unspassword@localhost:5432/unsdb"
    emqx_host: str = "localhost"
    emqx_port: int = 1883
    emqx_client_id: str = "uns_manager"


settings = Settings()
```

- [ ] **Step 2: Create backend/app/database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    from app.models import uns  # noqa: F401 — registers models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 3: Create backend/app/models/__init__.py**

```python
```
(empty file)

---

## Task 4: Backend — SQLAlchemy Models (uns.py)

**Files:**
- Create: `backend/app/models/uns.py`

- [ ] **Step 1: Write ORM models**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    cell: Mapped[Cell] = relationship("Cell", back_populates="assets")
```

---

## Task 5: Backend — Pydantic v2 Schemas

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/uns.py`

- [ ] **Step 1: Create backend/app/schemas/__init__.py**

```python
```
(empty)

- [ ] **Step 2: Create backend/app/schemas/uns.py**

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

    model_config = ConfigDict(populate_by_name=True)


class EnterpriseRead(_Base):
    id: str
    name: str
    description: str | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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

    model_config = ConfigDict(populate_by_name=True)


class SiteRead(_Base):
    id: str
    enterprise_id: str
    name: str
    description: str | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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

    model_config = ConfigDict(populate_by_name=True)


class AreaRead(_Base):
    id: str
    site_id: str
    name: str
    description: str | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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

    model_config = ConfigDict(populate_by_name=True)


class LineRead(_Base):
    id: str
    area_id: str
    name: str
    description: str | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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

    model_config = ConfigDict(populate_by_name=True)


class CellRead(_Base):
    id: str
    line_id: str
    name: str
    description: str | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ─── Asset ────────────────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    descriptive_payload: dict[str, Any] | None = None


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    descriptive_payload: dict[str, Any] | None = None


class AssetRead(_Base):
    id: str
    cell_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    uns_topic: str | None
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

---

## Task 6: Backend — Services (UNS topic + MQTT publish)

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/uns_service.py`
- Create: `backend/app/services/mqtt_service.py`

- [ ] **Step 1: Create backend/app/services/__init__.py**

```python
```
(empty)

- [ ] **Step 2: Create backend/app/services/uns_service.py**

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.uns import Asset, Cell, Line, Area, Site, Enterprise


async def build_uns_topic(asset: Asset, db: AsyncSession) -> str:
    """Builds the full UNS topic path for an asset by walking up the hierarchy."""
    cell = await db.get(Cell, asset.cell_id)
    line = await db.get(Line, cell.line_id)
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)

    parts = [
        enterprise.name,
        site.name,
        area.name,
        line.name,
        cell.name,
        asset.name,
        "_descriptive",
    ]
    return "/".join(p.replace(" ", "_") for p in parts)
```

- [ ] **Step 3: Create backend/app/services/mqtt_service.py**

```python
from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from app.config import settings

logger = logging.getLogger(__name__)

_client: mqtt.Client | None = None


def get_mqtt_client() -> mqtt.Client:
    global _client
    if _client is None or not _client.is_connected():
        _client = mqtt.Client(client_id=settings.emqx_client_id, protocol=mqtt.MQTTv5)
        _client.connect(settings.emqx_host, settings.emqx_port, keepalive=60)
        _client.loop_start()
    return _client


def publish_descriptive(topic: str, payload: dict[str, Any]) -> None:
    client = get_mqtt_client()
    message = json.dumps(payload, ensure_ascii=False, default=str)
    result = client.publish(topic, message, qos=1, retain=True)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        logger.error("MQTT publish failed rc=%s topic=%s", result.rc, topic)
    else:
        logger.info("Published _descriptive to %s", topic)


def disconnect_mqtt() -> None:
    global _client
    if _client:
        _client.loop_stop()
        _client.disconnect()
        _client = None
```

---

## Task 7: Backend — Router: enterprises.py

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/enterprises.py`

- [ ] **Step 1: Create backend/app/routers/__init__.py**

```python
```
(empty)

- [ ] **Step 2: Create backend/app/routers/enterprises.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Enterprise
from app.schemas.uns import EnterpriseCreate, EnterpriseRead, EnterpriseUpdate

router = APIRouter(prefix="/enterprises", tags=["Enterprises"])


@router.get("/", response_model=list[EnterpriseRead])
async def list_enterprises(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Enterprise).order_by(Enterprise.name))
    return result.scalars().all()


@router.post("/", response_model=EnterpriseRead, status_code=status.HTTP_201_CREATED)
async def create_enterprise(body: EnterpriseCreate, db: AsyncSession = Depends(get_db)):
    obj = Enterprise(
        name=body.name,
        description=body.description,
        metadata_=body.metadata_,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{enterprise_id}", response_model=EnterpriseRead)
async def get_enterprise(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    return obj


@router.patch("/{enterprise_id}", response_model=EnterpriseRead)
async def update_enterprise(enterprise_id: str, body: EnterpriseUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{enterprise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enterprise(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    await db.delete(obj)
    await db.commit()
```

---

## Task 8: Backend — Routers: sites, areas, lines, cells

**Files:**
- Create: `backend/app/routers/sites.py`
- Create: `backend/app/routers/areas.py`
- Create: `backend/app/routers/lines.py`
- Create: `backend/app/routers/cells.py`

- [ ] **Step 1: Create backend/app/routers/sites.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Site, Enterprise
from app.schemas.uns import SiteCreate, SiteRead, SiteUpdate

router = APIRouter(prefix="/enterprises/{enterprise_id}/sites", tags=["Sites"])


@router.get("/", response_model=list[SiteRead])
async def list_sites(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).where(Site.enterprise_id == enterprise_id).order_by(Site.name))
    return result.scalars().all()


@router.post("/", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
async def create_site(enterprise_id: str, body: SiteCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Enterprise, enterprise_id):
        raise HTTPException(status_code=404, detail="Enterprise not found")
    obj = Site(enterprise_id=enterprise_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{site_id}", response_model=SiteRead)
async def get_site(enterprise_id: str, site_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    return obj


@router.patch("/{site_id}", response_model=SiteRead)
async def update_site(enterprise_id: str, site_id: str, body: SiteUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(enterprise_id: str, site_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    await db.delete(obj)
    await db.commit()
```

- [ ] **Step 2: Create backend/app/routers/areas.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Area, Site
from app.schemas.uns import AreaCreate, AreaRead, AreaUpdate

router = APIRouter(prefix="/sites/{site_id}/areas", tags=["Areas"])


@router.get("/", response_model=list[AreaRead])
async def list_areas(site_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area).where(Area.site_id == site_id).order_by(Area.name))
    return result.scalars().all()


@router.post("/", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
async def create_area(site_id: str, body: AreaCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Site, site_id):
        raise HTTPException(status_code=404, detail="Site not found")
    obj = Area(site_id=site_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{area_id}", response_model=AreaRead)
async def get_area(site_id: str, area_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    return obj


@router.patch("/{area_id}", response_model=AreaRead)
async def update_area(site_id: str, area_id: str, body: AreaUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_area(site_id: str, area_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    await db.delete(obj)
    await db.commit()
```

- [ ] **Step 3: Create backend/app/routers/lines.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Line, Area
from app.schemas.uns import LineCreate, LineRead, LineUpdate

router = APIRouter(prefix="/areas/{area_id}/lines", tags=["Lines"])


@router.get("/", response_model=list[LineRead])
async def list_lines(area_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Line).where(Line.area_id == area_id).order_by(Line.name))
    return result.scalars().all()


@router.post("/", response_model=LineRead, status_code=status.HTTP_201_CREATED)
async def create_line(area_id: str, body: LineCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Area, area_id):
        raise HTTPException(status_code=404, detail="Area not found")
    obj = Line(area_id=area_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{line_id}", response_model=LineRead)
async def get_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    return obj


@router.patch("/{line_id}", response_model=LineRead)
async def update_line(area_id: str, line_id: str, body: LineUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    await db.delete(obj)
    await db.commit()
```

- [ ] **Step 4: Create backend/app/routers/cells.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Cell, Line
from app.schemas.uns import CellCreate, CellRead, CellUpdate

router = APIRouter(prefix="/lines/{line_id}/cells", tags=["Cells"])


@router.get("/", response_model=list[CellRead])
async def list_cells(line_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cell).where(Cell.line_id == line_id).order_by(Cell.name))
    return result.scalars().all()


@router.post("/", response_model=CellRead, status_code=status.HTTP_201_CREATED)
async def create_cell(line_id: str, body: CellCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Line, line_id):
        raise HTTPException(status_code=404, detail="Line not found")
    obj = Cell(line_id=line_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{cell_id}", response_model=CellRead)
async def get_cell(line_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    return obj


@router.patch("/{cell_id}", response_model=CellRead)
async def update_cell(line_id: str, cell_id: str, body: CellUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{cell_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cell(line_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    await db.delete(obj)
    await db.commit()
```

---

## Task 9: Backend — Router: assets.py (with MQTT publish)

**Files:**
- Create: `backend/app/routers/assets.py`

- [ ] **Step 1: Create backend/app/routers/assets.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Asset, Cell
from app.schemas.uns import AssetCreate, AssetRead, AssetUpdate
from app.services.uns_service import build_uns_topic
from app.services.mqtt_service import publish_descriptive

router = APIRouter(prefix="/cells/{cell_id}/assets", tags=["Assets"])


@router.get("/", response_model=list[AssetRead])
async def list_assets(cell_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.cell_id == cell_id).order_by(Asset.name))
    return result.scalars().all()


@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(cell_id: str, body: AssetCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Cell, cell_id):
        raise HTTPException(status_code=404, detail="Cell not found")
    obj = Asset(
        cell_id=cell_id,
        name=body.name,
        description=body.description,
        descriptive_payload=body.descriptive_payload or {},
    )
    db.add(obj)
    await db.flush()  # get ID before commit

    topic = await build_uns_topic(obj, db)
    obj.uns_topic = topic

    await db.commit()
    await db.refresh(obj)

    if obj.descriptive_payload:
        try:
            publish_descriptive(topic, obj.descriptive_payload)
        except Exception:
            pass  # MQTT publish is best-effort; don't fail the HTTP request

    return obj


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return obj


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(cell_id: str, asset_id: str, body: AssetUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    if body.name is not None:
        obj.uns_topic = await build_uns_topic(obj, db)

    await db.commit()
    await db.refresh(obj)

    if obj.descriptive_payload and obj.uns_topic:
        try:
            publish_descriptive(obj.uns_topic, obj.descriptive_payload)
        except Exception:
            pass

    return obj


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    await db.delete(obj)
    await db.commit()


@router.post("/{asset_id}/publish", response_model=AssetRead)
async def publish_asset(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    """Force re-publish the _descriptive payload to EMQX."""
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not obj.uns_topic:
        obj.uns_topic = await build_uns_topic(obj, db)
        await db.commit()
        await db.refresh(obj)
    if obj.descriptive_payload:
        publish_descriptive(obj.uns_topic, obj.descriptive_payload)
    return obj
```

---

## Task 10: Backend — Tree endpoint + main.py

**Files:**
- Create: `backend/app/routers/tree.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Create backend/app/routers/tree.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.uns import Enterprise
from app.schemas.uns import EnterpriseTree

router = APIRouter(prefix="/tree", tags=["Tree"])


@router.get("/", response_model=list[EnterpriseTree])
async def get_full_tree(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Enterprise)
        .options(
            selectinload(Enterprise.sites)
            .selectinload("areas")
            .selectinload("lines")
            .selectinload("cells")
            .selectinload("assets")
        )
        .order_by(Enterprise.name)
    )
    return result.scalars().all()
```

- [ ] **Step 2: Create backend/app/main.py**

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_tables
from app.routers import enterprises, sites, areas, lines, cells, assets, tree
from app.services.mqtt_service import disconnect_mqtt

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield
    disconnect_mqtt()


app = FastAPI(
    title="UNS Manager",
    description="Unified Namespace Manager — ISA-95 hierarchy + EMQX integration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enterprises.router)
app.include_router(sites.router)
app.include_router(areas.router)
app.include_router(lines.router)
app.include_router(cells.router)
app.include_router(assets.router)
app.include_router(tree.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 3: Update backend/app/routers/__init__.py**

```python
from app.routers import enterprises, sites, areas, lines, cells, assets, tree

__all__ = ["enterprises", "sites", "areas", "lines", "cells", "assets", "tree"]
```

---

## Task 11: Frontend — Scaffold (package.json, Vite, Tailwind, tsconfig)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`

- [ ] **Step 1: Create frontend/package.json**

```json
{
  "name": "uns-manager-frontend",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.7.9",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.16",
    "typescript": "^5.7.2",
    "vite": "^6.0.3"
  }
}
```

- [ ] **Step 2: Create frontend/vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE_URL || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
```

- [ ] **Step 3: Create frontend/tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

- [ ] **Step 4: Create frontend/postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Create frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 6: Create frontend/index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>UNS Manager</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

## Task 12: Frontend — TypeScript types + API client

**Files:**
- Create: `frontend/src/types/uns.ts`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Create frontend/src/types/uns.ts**

```typescript
export interface Enterprise {
  id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Site {
  id: string;
  enterprise_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Area {
  id: string;
  site_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Line {
  id: string;
  area_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Cell {
  id: string;
  line_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  cell_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  uns_topic: string | null;
  created_at: string;
  updated_at: string;
}

export interface CellTree extends Cell {
  assets: Asset[];
}

export interface LineTree extends Line {
  cells: CellTree[];
}

export interface AreaTree extends Area {
  lines: LineTree[];
}

export interface SiteTree extends Site {
  areas: AreaTree[];
}

export interface EnterpriseTree extends Enterprise {
  sites: SiteTree[];
}

export type HierarchyLevel = "enterprise" | "site" | "area" | "line" | "cell" | "asset";

export interface SelectedNode {
  level: HierarchyLevel;
  id: string;
  parentIds: Record<string, string>;
}
```

- [ ] **Step 2: Create frontend/src/api/client.ts**

```typescript
import axios from "axios";
import type { Asset, Area, Cell, Enterprise, EnterpriseTree, Line, Site } from "../types/uns";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const http = axios.create({ baseURL: BASE });

// ── Enterprises ─────────────────────────────────────────────────────────────

export const api = {
  tree: {
    get: () => http.get<EnterpriseTree[]>("/tree/").then((r) => r.data),
  },
  enterprises: {
    list: () => http.get<Enterprise[]>("/enterprises/").then((r) => r.data),
    get: (id: string) => http.get<Enterprise>(`/enterprises/${id}`).then((r) => r.data),
    create: (body: { name: string; description?: string; metadata?: Record<string, unknown> }) =>
      http.post<Enterprise>("/enterprises/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string; metadata: Record<string, unknown> }>) =>
      http.patch<Enterprise>(`/enterprises/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/enterprises/${id}`),
  },
  sites: {
    list: (enterpriseId: string) =>
      http.get<Site[]>(`/enterprises/${enterpriseId}/sites/`).then((r) => r.data),
    create: (enterpriseId: string, body: { name: string; description?: string }) =>
      http.post<Site>(`/enterprises/${enterpriseId}/sites/`, body).then((r) => r.data),
    update: (enterpriseId: string, siteId: string, body: Partial<{ name: string; description: string }>) =>
      http.patch<Site>(`/enterprises/${enterpriseId}/sites/${siteId}`, body).then((r) => r.data),
    delete: (enterpriseId: string, siteId: string) =>
      http.delete(`/enterprises/${enterpriseId}/sites/${siteId}`),
  },
  areas: {
    list: (siteId: string) => http.get<Area[]>(`/sites/${siteId}/areas/`).then((r) => r.data),
    create: (siteId: string, body: { name: string; description?: string }) =>
      http.post<Area>(`/sites/${siteId}/areas/`, body).then((r) => r.data),
    update: (siteId: string, areaId: string, body: Partial<{ name: string; description: string }>) =>
      http.patch<Area>(`/sites/${siteId}/areas/${areaId}`, body).then((r) => r.data),
    delete: (siteId: string, areaId: string) => http.delete(`/sites/${siteId}/areas/${areaId}`),
  },
  lines: {
    list: (areaId: string) => http.get<Line[]>(`/areas/${areaId}/lines/`).then((r) => r.data),
    create: (areaId: string, body: { name: string; description?: string }) =>
      http.post<Line>(`/areas/${areaId}/lines/`, body).then((r) => r.data),
    update: (areaId: string, lineId: string, body: Partial<{ name: string; description: string }>) =>
      http.patch<Line>(`/areas/${areaId}/lines/${lineId}`, body).then((r) => r.data),
    delete: (areaId: string, lineId: string) => http.delete(`/areas/${areaId}/lines/${lineId}`),
  },
  cells: {
    list: (lineId: string) => http.get<Cell[]>(`/lines/${lineId}/cells/`).then((r) => r.data),
    create: (lineId: string, body: { name: string; description?: string }) =>
      http.post<Cell>(`/lines/${lineId}/cells/`, body).then((r) => r.data),
    update: (lineId: string, cellId: string, body: Partial<{ name: string; description: string }>) =>
      http.patch<Cell>(`/lines/${lineId}/cells/${cellId}`, body).then((r) => r.data),
    delete: (lineId: string, cellId: string) => http.delete(`/lines/${lineId}/cells/${cellId}`),
  },
  assets: {
    list: (cellId: string) => http.get<Asset[]>(`/cells/${cellId}/assets/`).then((r) => r.data),
    create: (cellId: string, body: { name: string; description?: string; descriptive_payload?: Record<string, unknown> }) =>
      http.post<Asset>(`/cells/${cellId}/assets/`, body).then((r) => r.data),
    update: (cellId: string, assetId: string, body: Partial<{ name: string; description: string; descriptive_payload: Record<string, unknown> }>) =>
      http.patch<Asset>(`/cells/${cellId}/assets/${assetId}`, body).then((r) => r.data),
    delete: (cellId: string, assetId: string) => http.delete(`/cells/${cellId}/assets/${assetId}`),
    publish: (cellId: string, assetId: string) =>
      http.post<Asset>(`/cells/${cellId}/assets/${assetId}/publish`).then((r) => r.data),
  },
};
```

---

## Task 13: Frontend — UnsTree component

**Files:**
- Create: `frontend/src/components/UnsTree.tsx`

- [ ] **Step 1: Create frontend/src/components/UnsTree.tsx**

```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { EnterpriseTree, SiteTree, AreaTree, LineTree, CellTree, Asset, SelectedNode } from "../types/uns";

interface Props {
  tree: EnterpriseTree[];
  onSelect: (node: SelectedNode) => void;
  selected: SelectedNode | null;
  onRefresh: () => void;
}

const LEVEL_COLORS: Record<string, string> = {
  enterprise: "text-purple-700 font-bold",
  site: "text-blue-700 font-semibold",
  area: "text-green-700 font-semibold",
  line: "text-yellow-700",
  cell: "text-orange-700",
  asset: "text-red-700",
};

function NodeRow({
  label,
  level,
  id,
  selected,
  onClick,
  onDelete,
  children,
}: {
  label: string;
  level: string;
  id: string;
  selected: boolean;
  onClick: () => void;
  onDelete: () => void;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div className="ml-3 border-l border-gray-200 pl-2">
      <div
        className={`flex items-center gap-1 py-0.5 cursor-pointer rounded px-1 hover:bg-gray-100 ${selected ? "bg-blue-50 ring-1 ring-blue-300" : ""}`}
      >
        <button onClick={() => setOpen(!open)} className="text-gray-400 w-4 shrink-0 text-xs">
          {children ? (open ? "▾" : "▸") : "·"}
        </button>
        <span onClick={onClick} className={`flex-1 text-sm ${LEVEL_COLORS[level] ?? ""}`}>
          {label}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="text-gray-300 hover:text-red-500 text-xs px-1"
          title="Delete"
        >
          ✕
        </button>
      </div>
      {open && children}
    </div>
  );
}

export function UnsTree({ tree, onSelect, selected, onRefresh }: Props) {
  const handleDelete = async (action: () => Promise<unknown>) => {
    if (!confirm("Delete this node and all its children?")) return;
    await action();
    onRefresh();
  };

  return (
    <div className="overflow-y-auto h-full text-sm select-none">
      {tree.map((enterprise) => (
        <NodeRow
          key={enterprise.id}
          label={enterprise.name}
          level="enterprise"
          id={enterprise.id}
          selected={selected?.level === "enterprise" && selected.id === enterprise.id}
          onClick={() => onSelect({ level: "enterprise", id: enterprise.id, parentIds: {} })}
          onDelete={() => handleDelete(() => api.enterprises.delete(enterprise.id).then(onRefresh))}
        >
          {enterprise.sites.map((site: SiteTree) => (
            <NodeRow
              key={site.id}
              label={site.name}
              level="site"
              id={site.id}
              selected={selected?.level === "site" && selected.id === site.id}
              onClick={() => onSelect({ level: "site", id: site.id, parentIds: { enterprise_id: enterprise.id } })}
              onDelete={() => handleDelete(() => api.sites.delete(enterprise.id, site.id).then(onRefresh))}
            >
              {site.areas.map((area: AreaTree) => (
                <NodeRow
                  key={area.id}
                  label={area.name}
                  level="area"
                  id={area.id}
                  selected={selected?.level === "area" && selected.id === area.id}
                  onClick={() => onSelect({ level: "area", id: area.id, parentIds: { site_id: site.id } })}
                  onDelete={() => handleDelete(() => api.areas.delete(site.id, area.id).then(onRefresh))}
                >
                  {area.lines.map((line: LineTree) => (
                    <NodeRow
                      key={line.id}
                      label={line.name}
                      level="line"
                      id={line.id}
                      selected={selected?.level === "line" && selected.id === line.id}
                      onClick={() => onSelect({ level: "line", id: line.id, parentIds: { area_id: area.id } })}
                      onDelete={() => handleDelete(() => api.lines.delete(area.id, line.id).then(onRefresh))}
                    >
                      {line.cells.map((cell: CellTree) => (
                        <NodeRow
                          key={cell.id}
                          label={cell.name}
                          level="cell"
                          id={cell.id}
                          selected={selected?.level === "cell" && selected.id === cell.id}
                          onClick={() => onSelect({ level: "cell", id: cell.id, parentIds: { line_id: line.id } })}
                          onDelete={() => handleDelete(() => api.cells.delete(line.id, cell.id).then(onRefresh))}
                        >
                          {cell.assets.map((asset: Asset) => (
                            <NodeRow
                              key={asset.id}
                              label={asset.name}
                              level="asset"
                              id={asset.id}
                              selected={selected?.level === "asset" && selected.id === asset.id}
                              onClick={() => onSelect({ level: "asset", id: asset.id, parentIds: { cell_id: cell.id } })}
                              onDelete={() => handleDelete(() => api.assets.delete(cell.id, asset.id).then(onRefresh))}
                            />
                          ))}
                        </NodeRow>
                      ))}
                    </NodeRow>
                  ))}
                </NodeRow>
              ))}
            </NodeRow>
          ))}
        </NodeRow>
      ))}
    </div>
  );
}
```

---

## Task 14: Frontend — NodeForm, JsonEditor, AssetDetail

**Files:**
- Create: `frontend/src/components/NodeForm.tsx`
- Create: `frontend/src/components/JsonEditor.tsx`
- Create: `frontend/src/components/AssetDetail.tsx`

- [ ] **Step 1: Create frontend/src/components/NodeForm.tsx**

```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { HierarchyLevel, SelectedNode } from "../types/uns";

interface Props {
  onCreated: () => void;
  selected: SelectedNode | null;
}

const CHILD_LEVEL: Record<HierarchyLevel, HierarchyLevel | null> = {
  enterprise: "site",
  site: "area",
  area: "line",
  line: "cell",
  cell: "asset",
  asset: null,
};

const LABELS: Record<HierarchyLevel, string> = {
  enterprise: "Enterprise",
  site: "Site",
  area: "Area",
  line: "Line",
  cell: "Cell",
  asset: "Asset",
};

export function NodeForm({ onCreated, selected }: Props) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);

  const parentLevel = selected?.level ?? null;
  const childLevel = parentLevel ? CHILD_LEVEL[parentLevel] : "enterprise";

  if (childLevel === null) return <p className="text-sm text-gray-500">Assets cannot have children.</p>;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const body = { name: name.trim(), description: desc.trim() || undefined };
      if (childLevel === "enterprise") {
        await api.enterprises.create(body);
      } else if (childLevel === "site" && selected) {
        await api.sites.create(selected.id, body);
      } else if (childLevel === "area" && selected) {
        await api.areas.create(selected.id, body);
      } else if (childLevel === "line" && selected) {
        await api.lines.create(selected.id, body);
      } else if (childLevel === "cell" && selected) {
        await api.cells.create(selected.id, body);
      } else if (childLevel === "asset" && selected) {
        await api.assets.create(selected.id, { ...body, descriptive_payload: {} });
      }
      setName("");
      setDesc("");
      onCreated();
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <p className="text-xs text-gray-500 uppercase tracking-wide">
        Add {LABELS[childLevel]}
        {parentLevel ? ` under selected ${LABELS[parentLevel]}` : ""}
      </p>
      <input
        className="w-full border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        placeholder={`${LABELS[childLevel]} name*`}
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <input
        className="w-full border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        placeholder="Description (optional)"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="w-full bg-blue-600 text-white text-sm py-1 rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {busy ? "Creating…" : `Create ${LABELS[childLevel]}`}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Create frontend/src/components/JsonEditor.tsx**

```tsx
import { useEffect, useState } from "react";

interface Props {
  value: Record<string, unknown> | null;
  onChange: (value: Record<string, unknown>) => void;
  disabled?: boolean;
}

export function JsonEditor({ value, onChange, disabled }: Props) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(JSON.stringify(value ?? {}, null, 2));
  }, [value]);

  const handleChange = (raw: string) => {
    setText(raw);
    try {
      const parsed = JSON.parse(raw);
      setError(null);
      onChange(parsed);
    } catch {
      setError("Invalid JSON");
    }
  };

  return (
    <div className="space-y-1">
      <textarea
        disabled={disabled}
        className={`w-full h-56 font-mono text-xs border rounded p-2 focus:outline-none focus:ring-1 focus:ring-blue-400 resize-y ${error ? "border-red-400" : "border-gray-300"}`}
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        spellCheck={false}
      />
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Create frontend/src/components/AssetDetail.tsx**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Asset } from "../types/uns";
import { JsonEditor } from "./JsonEditor";

interface Props {
  cellId: string;
  assetId: string;
  onSaved: () => void;
}

export function AssetDetail({ cellId, assetId, onSaved }: Props) {
  const [asset, setAsset] = useState<Asset | null>(null);
  const [payload, setPayload] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [published, setPublished] = useState(false);

  useEffect(() => {
    api.assets.list(cellId).then((assets) => {
      const found = assets.find((a) => a.id === assetId);
      if (found) {
        setAsset(found);
        setPayload(found.descriptive_payload ?? {});
      }
    });
  }, [cellId, assetId]);

  const handleSave = async () => {
    if (!asset) return;
    setBusy(true);
    try {
      const updated = await api.assets.update(cellId, assetId, { descriptive_payload: payload });
      setAsset(updated);
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  const handlePublish = async () => {
    if (!asset) return;
    setBusy(true);
    try {
      await api.assets.update(cellId, assetId, { descriptive_payload: payload });
      await api.assets.publish(cellId, assetId);
      setPublished(true);
      setTimeout(() => setPublished(false), 3000);
    } finally {
      setBusy(false);
    }
  };

  if (!asset) return <p className="text-sm text-gray-400 p-4">Loading asset…</p>;

  return (
    <div className="p-4 space-y-4">
      <div>
        <h2 className="text-lg font-bold text-gray-800">{asset.name}</h2>
        {asset.description && <p className="text-sm text-gray-500">{asset.description}</p>}
        {asset.uns_topic && (
          <p className="text-xs font-mono mt-1 bg-gray-100 rounded px-2 py-1 text-gray-600 break-all">
            {asset.uns_topic}
          </p>
        )}
      </div>

      <div>
        <label className="block text-xs uppercase tracking-wide text-gray-500 mb-1">
          _descriptive Payload (JSON)
        </label>
        <JsonEditor value={asset.descriptive_payload} onChange={setPayload} disabled={busy} />
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={busy}
          className="flex-1 bg-gray-600 text-white text-sm py-1.5 rounded hover:bg-gray-700 disabled:opacity-50"
        >
          Save
        </button>
        <button
          onClick={handlePublish}
          disabled={busy}
          className="flex-1 bg-green-600 text-white text-sm py-1.5 rounded hover:bg-green-700 disabled:opacity-50"
        >
          {published ? "Published!" : "Save & Publish to EMQX"}
        </button>
      </div>
    </div>
  );
}
```

---

## Task 15: Frontend — App.tsx + main.tsx + CSS

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`

- [ ] **Step 1: Create frontend/src/index.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 2: Create frontend/src/App.tsx**

```tsx
import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import { UnsTree } from "./components/UnsTree";
import { NodeForm } from "./components/NodeForm";
import { AssetDetail } from "./components/AssetDetail";
import type { EnterpriseTree, SelectedNode } from "./types/uns";

export default function App() {
  const [tree, setTree] = useState<EnterpriseTree[]>([]);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.tree.get();
      setTree(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="flex h-screen bg-gray-50 text-gray-800 font-sans">
      {/* Sidebar — tree */}
      <aside className="w-72 flex flex-col border-r border-gray-200 bg-white">
        <header className="px-4 py-3 border-b border-gray-200">
          <h1 className="font-bold text-base tracking-tight">UNS Manager</h1>
          <p className="text-xs text-gray-400">ISA-95 Hierarchy</p>
        </header>

        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <p className="text-xs text-gray-400 p-2">Loading…</p>
          ) : (
            <UnsTree
              tree={tree}
              onSelect={setSelected}
              selected={selected}
              onRefresh={refresh}
            />
          )}
        </div>

        <div className="p-3 border-t border-gray-100">
          <NodeForm onCreated={refresh} selected={selected} />
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {selected?.level === "asset" && selected.parentIds.cell_id ? (
          <AssetDetail
            cellId={selected.parentIds.cell_id}
            assetId={selected.id}
            onSaved={refresh}
          />
        ) : selected ? (
          <div className="p-6">
            <p className="text-gray-500 text-sm capitalize">
              Selected <strong>{selected.level}</strong> — select an <strong>Asset</strong> to edit its{" "}
              <code className="text-xs bg-gray-100 px-1 rounded">_descriptive</code> payload.
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            Select a node in the tree to get started.
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Create frontend/src/main.tsx**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

---

## Task 16: Frontend — Dockerfile

**Files:**
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Create frontend/Dockerfile**

```dockerfile
# Build stage
FROM node:22-alpine AS builder
WORKDIR /app
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json .
RUN npm install

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: Create frontend/nginx.conf**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Task 17: Verification — Build & Smoke Test

- [ ] **Step 1: Copy .env.example to .env (if not done)**

```bash
cp .env.example .env
```

- [ ] **Step 2: Build and start all services**

```bash
cd G:/00_data/00_Formacion/INARI_V04
docker compose up --build -d
```

Expected: All 4 containers start. Check with `docker compose ps`.

- [ ] **Step 3: Verify backend health**

```bash
curl http://localhost:8000/health
```

Expected response: `{"status": "ok"}`

- [ ] **Step 4: Create sample Enterprise via API**

```bash
curl -X POST http://localhost:8000/enterprises/ \
  -H "Content-Type: application/json" \
  -d '{"name": "ACME Corp", "description": "Test enterprise"}'
```

Expected: 201 response with Enterprise JSON including `id`.

- [ ] **Step 5: Verify frontend is accessible**

Open `http://localhost:3000` in a browser.

Expected: UNS Manager UI loads with empty tree.

- [ ] **Step 6: End-to-end flow**

Via the UI:
1. Create Enterprise → Site → Area → Line → Cell → Asset
2. Select the Asset, edit the JSON payload, click "Save & Publish to EMQX"
3. Verify in EMQX Dashboard (http://localhost:18083, admin/public) the retained message under the UNS topic

- [ ] **Step 7: Verify API docs**

Open `http://localhost:8000/docs` — FastAPI Swagger UI should show all endpoints.

---

## Self-Review

**Spec coverage check:**
- ✅ PostgreSQL as source of truth (models + asyncpg)
- ✅ ISA-95 levels: Enterprise / Site / Area / Line / Cell / Asset
- ✅ `_descriptive` payload in JSONB, managed by UNS Manager
- ✅ UNS topic format: `Enterprise/Site/Area/Line/Cell/Asset/_descriptive`
- ✅ EMQX publish via paho-mqtt (retained, QoS 1)
- ✅ FastAPI backend with full CRUD for all levels
- ✅ React + TypeScript + Vite + Tailwind frontend
- ✅ Docker Compose with postgres, emqx, backend, frontend services
- ✅ Tree view of full hierarchy
- ✅ Asset detail + JSON editor for _descriptive payload
- ✅ .env.example

**Placeholder scan:** No TBDs or "implement later" found.

**Type consistency:** `EnterpriseTree`, `SiteTree`, `AreaTree`, `LineTree`, `CellTree` used consistently in both TypeScript types and Pydantic schemas.
