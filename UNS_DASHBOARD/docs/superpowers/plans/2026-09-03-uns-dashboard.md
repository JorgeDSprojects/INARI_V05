# UNS Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `UNS_DASHBOARD`, a new independently deployable module that lets a user author SCADA-style dashboards (react-grid-layout) mixing live-streamed and historical `_informative` signals, and publish them to a read-only production view.

**Architecture:** `EMQX → bridge (MQTT subscriber) → Redis Streams → FastAPI backend (WebSocket + REST) → React frontend`. The backend owns a dedicated Postgres for dashboard/chart definitions and reads `UNS_HISTORIAN`'s Postgres read-only for history/signal-catalog/backfill. See the design spec for full rationale.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async, asyncpg), paho-mqtt 2.1, redis-py (asyncio), pytest; React 18 + TypeScript + Vite, react-grid-layout, recharts, axios, Tailwind; Docker Compose.

**Spec:** `UNS_DASHBOARD/docs/superpowers/specs/2026-09-03-uns-dashboard-design.md`

## Global Constraints

- Code, identifiers, comments, and commit messages: English (per `AGENTS.md`).
- Every runnable service gets a `Dockerfile`; local orchestration via `docker compose` (per `AGENTS.md` §2).
- Inter-container calls use Docker service DNS names, never `localhost` (per `AGENTS.md` §3).
- `scripts/{up,down,restart,logs,status}.sh` required, `set -euo pipefail` (per `AGENTS.md` §4).
- Config via environment variables; `.env.example` documents every variable; real `.env` stays git-ignored (per `AGENTS.md` §5).
- Real-time transport is `EMQX → bridge → Redis Streams → backend WebSocket → browser`. The browser never opens an MQTT connection. Future consumers (ML/alerting) subscribe to EMQX directly, never to this module's Redis.
- Data mode (`live`/`historical`) is set per chart, not per dashboard.
- Historical downsampling always targets ~500–1000 points via `time_bucket`; bucket width = `range_seconds / 750` snapped to `[1s, 5s, 30s, 1m, 5m, 1h, 1d]`.
- No authentication in v1 (matches `UNS_MANAGER`/`UNS_HISTORIAN`).
- DB-touching tests follow `UNS_HISTORIAN`'s convention: `pytest.mark.skipif(not DATABASE_URL, ...)`, gated on a live Postgres started via `docker compose up -d`, with a fixture that deletes its own `pytest/`-prefixed rows before and after.
- Pure logic (parsing, filtering, range math, fan-out bookkeeping) is unit tested with no live services; thin async I/O glue (MQTT wiring, Redis stream readers) is verified manually, mirroring `UNS_HISTORIAN`'s own testing scope decision.

---

## File Structure

```
UNS_DASHBOARD/
  docker-compose.yml
  .env.example
  .gitignore
  README.md
  scripts/{up,down,restart,logs,status}.sh
  docs/superpowers/specs/2026-09-03-uns-dashboard-design.md   (already committed)
  docs/superpowers/plans/2026-09-03-uns-dashboard.md          (this file)
  postgres/init.sql

  backend/
    Dockerfile
    requirements.txt
    app/
      config.py
      database.py
      main.py
      models/dashboard.py
      schemas/dashboard.py
      routers/dashboards.py
      routers/charts.py
      routers/signals.py
      routers/history.py
      routers/stream.py
      services/historian_query.py
      services/descriptive_lookup.py
      services/ws_manager.py
      services/redis_client.py
    tests/
      conftest.py
      test_historian_query.py
      test_descriptive_lookup.py
      test_ws_manager.py
      test_dashboards_router.py
      test_charts_router.py
      test_history_router.py
      test_signals_router.py

  bridge/
    Dockerfile
    requirements.txt
    app/
      config.py
      filter.py
      stream_writer.py
      main.py
    tests/
      test_filter.py
      test_stream_writer.py

  frontend/
    Dockerfile
    nginx.conf
    package.json
    vite.config.ts
    tsconfig.json
    tailwind.config.js
    postcss.config.js
    index.html
    src/
      main.tsx
      App.tsx
      api/client.ts
      types/dashboard.ts
      lib/refreshInterval.ts
      pages/MenuPage.tsx
      pages/EditorPage.tsx
      pages/ViewerPage.tsx
      components/ChartCardShell.tsx
      components/charts/TimeSeriesChart.tsx
      components/charts/BarChart.tsx
      components/charts/GaugeChart.tsx
      components/charts/KpiTile.tsx
      components/charts/StatusIndicator.tsx
      components/charts/ValuesTable.tsx
      components/editor/GridWorkspace.tsx
      components/editor/DashboardMetaForm.tsx
      components/editor/ChartForm.tsx
      components/editor/SignalPicker.tsx
      components/editor/PendingChartsList.tsx
      hooks/useDashboardSocket.ts
      hooks/useHistoricalQuery.ts
    src/lib/__tests__/refreshInterval.test.ts
    src/components/charts/__tests__/GaugeChart.test.tsx
    src/components/charts/__tests__/TimeSeriesChart.test.tsx
    src/hooks/__tests__/useDashboardSocket.test.ts
    vitest.config.ts
```

Root repo changes:
- `docker-compose.yml` — add `UNS_DASHBOARD/docker-compose.yml` to `include:`.
- `UNS_HISTORIAN/docker-compose.yml` — `historian_postgres` additionally joins `uns_manager_net`.

---

## Task 1: Backend foundation (config, DB engine, FastAPI skeleton)

**Files:**
- Create: `UNS_DASHBOARD/backend/app/config.py`
- Create: `UNS_DASHBOARD/backend/app/database.py`
- Create: `UNS_DASHBOARD/backend/app/main.py`
- Create: `UNS_DASHBOARD/backend/requirements.txt`
- Create: `UNS_DASHBOARD/backend/Dockerfile`
- Create: `UNS_DASHBOARD/backend/tests/conftest.py`
- Test: `UNS_DASHBOARD/backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.config.settings: Settings` (fields: `database_url`, `historian_database_url`, `emqx_host`, `emqx_port`, `emqx_api_port`, `redis_host`, `redis_port`, `stream_maxlen`); `app.database.Base`, `app.database.get_db`, `app.database.create_tables`; `app.main.app: FastAPI`.

- [ ] **Step 1: Write requirements.txt**

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
pydantic-settings==2.7.0
httpx==0.28.1
redis==5.2.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Write the failing test**

```python
# UNS_DASHBOARD/backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && pip install -r requirements.txt && pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 4: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard"
    historian_database_url: str = "postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian"
    emqx_host: str = "localhost"
    emqx_port: int = 1883
    emqx_api_port: int = 18083
    emqx_api_username: str | None = None
    emqx_api_password: str | None = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    stream_maxlen: int = 1000


settings = Settings()
```

- [ ] **Step 5: Write `app/database.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

historian_engine = create_async_engine(settings.historian_database_url, echo=False, future=True)
HistorianSessionLocal = async_sessionmaker(historian_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def get_historian_db() -> AsyncSession:
    async with HistorianSessionLocal() as session:
        yield session


async def create_tables() -> None:
    from app.models import dashboard  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 6: Write a placeholder `app/models/dashboard.py` (models arrive in Task 2) and `app/main.py`**

```python
# UNS_DASHBOARD/backend/app/models/dashboard.py
# Populated in Task 2.
```

```python
# UNS_DASHBOARD/backend/app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_tables

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title="UNS Dashboard",
    description="Real-time SCADA dashboard authoring and viewing",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Write empty `tests/conftest.py` (package marker, shared fixtures land in later tasks)**

```python
# UNS_DASHBOARD/backend/tests/conftest.py
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 9: Write the Dockerfile**

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

- [ ] **Step 10: Commit**

```bash
git add UNS_DASHBOARD/backend
git commit -m "feat(uns-dashboard): backend skeleton with health endpoint"
```

---

## Task 2: Dashboard/Chart/ChartSignal models + Pydantic schemas

**Files:**
- Modify: `UNS_DASHBOARD/backend/app/models/dashboard.py`
- Create: `UNS_DASHBOARD/backend/app/schemas/dashboard.py`
- Test: `UNS_DASHBOARD/backend/tests/test_models.py`

**Interfaces:**
- Consumes: `app.database.Base` (Task 1).
- Produces: `Dashboard`, `Chart`, `ChartSignal` SQLAlchemy models; `DashboardCreate`, `DashboardUpdate`, `DashboardRead`, `ChartCreate`, `ChartUpdate`, `ChartRead`, `ChartSignalCreate`, `ChartSignalRead` Pydantic schemas — used by every router task from here on.

- [ ] **Step 1: Write the failing test**

```python
# UNS_DASHBOARD/backend/tests/test_models.py
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import Base
from app.models.dashboard import Dashboard, Chart, ChartSignal

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
async def session():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as s:
        yield s
        await s.execute(Chart.__table__.delete())
        await s.execute(Dashboard.__table__.delete())
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_chart_and_signal_cascade_from_dashboard(session: AsyncSession):
    dashboard = Dashboard(name="pytest Campo Sur", description="test")
    session.add(dashboard)
    await session.flush()

    chart = Chart(
        dashboard_id=dashboard.id,
        name="Temp General",
        chart_type="timeseries",
        data_mode="historical",
        historical_range_type="relative",
        historical_relative_rule="30d",
        layout_x=0, layout_y=0, layout_w=12, layout_h=4,
        color="#3B82F6",
    )
    session.add(chart)
    await session.flush()

    signal = ChartSignal(
        chart_id=chart.id, topic="Enterprise/Site/_informative", signal_key="Amb_Temp_Avg",
        label="Amb Temp", unit="°C", source="manual",
    )
    session.add(signal)
    await session.commit()

    await session.delete(dashboard)
    await session.commit()

    remaining_charts = (await session.execute(Chart.__table__.select())).fetchall()
    assert remaining_charts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Dashboard'`

- [ ] **Step 3: Write `app/models/dashboard.py`**

```python
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
```

- [ ] **Step 4: Write `app/schemas/dashboard.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard pytest tests/test_models.py -v`
Expected: PASS (skipped locally without `DATABASE_URL`; runs once Task 12's `docker compose up -d postgres` is available)

- [ ] **Step 6: Commit**

```bash
git add UNS_DASHBOARD/backend/app/models/dashboard.py UNS_DASHBOARD/backend/app/schemas/dashboard.py UNS_DASHBOARD/backend/tests/test_models.py
git commit -m "feat(uns-dashboard): dashboard/chart/chart_signal models and schemas"
```

---

## Task 3: Dashboards CRUD router

**Files:**
- Create: `UNS_DASHBOARD/backend/app/routers/dashboards.py`
- Modify: `UNS_DASHBOARD/backend/app/main.py`
- Test: `UNS_DASHBOARD/backend/tests/test_dashboards_router.py`

**Interfaces:**
- Consumes: `Dashboard` model, `DashboardCreate/Update/Read/DetailRead` schemas (Task 2), `get_db` (Task 1).
- Produces: router mounted at `/dashboards`, endpoints `GET /dashboards/`, `POST /dashboards/`, `GET /dashboards/{id}`, `PATCH /dashboards/{id}`, `DELETE /dashboards/{id}`, `POST /dashboards/{id}/publish`.

- [ ] **Step 1: Write the failing test**

```python
# UNS_DASHBOARD/backend/tests/test_dashboards_router.py
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, AsyncSessionLocal

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _cleanup():
    import asyncio
    from app.models.dashboard import Dashboard
    from sqlalchemy import delete

    async def _run():
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Dashboard).where(Dashboard.name.like("pytest%")))
            await s.commit()

    asyncio.run(_run())


def test_create_list_publish_delete_dashboard(client: TestClient):
    _cleanup()
    created = client.post("/dashboards/", json={"name": "pytest Campo Sur", "description": "desc"}).json()
    assert created["status"] == "draft"

    listed = client.get("/dashboards/").json()
    assert any(d["id"] == created["id"] for d in listed)

    published = client.post(f"/dashboards/{created['id']}/publish").json()
    assert published["status"] == "published"
    assert published["published_at"] is not None

    detail = client.get(f"/dashboards/{created['id']}").json()
    assert detail["charts"] == []

    client.delete(f"/dashboards/{created['id']}")
    assert client.get(f"/dashboards/{created['id']}").status_code == 404
    _cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard pytest tests/test_dashboards_router.py -v`
Expected: FAIL — 404 on `POST /dashboards/` (router not mounted)

- [ ] **Step 3: Write `app/routers/dashboards.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.dashboard import Dashboard
from app.schemas.dashboard import DashboardCreate, DashboardDetailRead, DashboardRead, DashboardUpdate

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("/", response_model=list[DashboardRead])
async def list_dashboards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dashboard).order_by(Dashboard.name))
    return result.scalars().all()


@router.post("/", response_model=DashboardRead, status_code=201)
async def create_dashboard(body: DashboardCreate, db: AsyncSession = Depends(get_db)):
    dashboard = Dashboard(name=body.name, description=body.description)
    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard


@router.get("/{dashboard_id}", response_model=DashboardDetailRead)
async def get_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id).options(selectinload(Dashboard.charts))
    )
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard


@router.patch("/{dashboard_id}", response_model=DashboardRead)
async def update_dashboard(dashboard_id: str, body: DashboardUpdate, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(dashboard, field, value)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    await db.delete(dashboard)
    await db.commit()


@router.post("/{dashboard_id}/publish", response_model=DashboardRead)
async def publish_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    dashboard.status = "published"
    dashboard.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard
```

- [ ] **Step 4: Wire it into `app/main.py`**

```python
# add near the top:
from app.routers import dashboards

# add after CORS middleware:
app.include_router(dashboards.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard pytest tests/test_dashboards_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add UNS_DASHBOARD/backend/app/routers/dashboards.py UNS_DASHBOARD/backend/app/main.py UNS_DASHBOARD/backend/tests/test_dashboards_router.py
git commit -m "feat(uns-dashboard): dashboards CRUD + publish endpoint"
```

---

## Task 4: Charts CRUD router (nested, with signals)

**Files:**
- Create: `UNS_DASHBOARD/backend/app/routers/charts.py`
- Modify: `UNS_DASHBOARD/backend/app/main.py`
- Test: `UNS_DASHBOARD/backend/tests/test_charts_router.py`

**Interfaces:**
- Consumes: `Chart`, `ChartSignal` models, `ChartCreate/Update/Read` schemas (Task 2).
- Produces: `POST /dashboards/{dashboard_id}/charts/`, `PATCH /charts/{chart_id}`, `DELETE /charts/{chart_id}` — `PATCH` with a `signals` field fully replaces the chart's signal list (simplest correct semantics; the editor always sends the full current list).

- [ ] **Step 1: Write the failing test**

```python
# UNS_DASHBOARD/backend/tests/test_charts_router.py
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import AsyncSessionLocal

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _cleanup():
    import asyncio
    from sqlalchemy import delete
    from app.models.dashboard import Dashboard

    async def _run():
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Dashboard).where(Dashboard.name.like("pytest%")))
            await s.commit()

    asyncio.run(_run())


def test_create_update_replace_signals_and_delete_chart(client: TestClient):
    _cleanup()
    dashboard = client.post("/dashboards/", json={"name": "pytest Campo Sur"}).json()

    chart = client.post(
        f"/dashboards/{dashboard['id']}/charts/",
        json={
            "name": "Temp General",
            "chart_type": "timeseries",
            "data_mode": "live",
            "layout_x": 0, "layout_y": 0, "layout_w": 12, "layout_h": 4,
            "signals": [{"topic": "a/b/_informative", "signal_key": "Amb_Temp_Avg", "unit": "°C"}],
        },
    ).json()
    assert len(chart["signals"]) == 1

    updated = client.patch(
        f"/charts/{chart['id']}",
        json={"signals": [
            {"topic": "a/b/_informative", "signal_key": "Amb_Temp_Avg", "unit": "°C"},
            {"topic": "a/b/_informative", "signal_key": "Gen_Bear_Temp_Avg", "unit": "°C"},
        ]},
    ).json()
    assert len(updated["signals"]) == 2

    client.delete(f"/charts/{chart['id']}")
    detail = client.get(f"/dashboards/{dashboard['id']}").json()
    assert detail["charts"] == []
    _cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard pytest tests/test_charts_router.py -v`
Expected: FAIL — 404 on `POST /dashboards/{id}/charts/`

- [ ] **Step 3: Write `app/routers/charts.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.database import get_db
from app.models.dashboard import Chart, ChartSignal, Dashboard
from app.schemas.dashboard import ChartCreate, ChartRead, ChartUpdate

router = APIRouter(tags=["charts"])


@router.post("/dashboards/{dashboard_id}/charts/", response_model=ChartRead, status_code=201)
async def create_chart(dashboard_id: str, body: ChartCreate, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    data = body.model_dump(exclude={"signals"})
    chart = Chart(dashboard_id=dashboard_id, **data)
    chart.signals = [ChartSignal(**s.model_dump()) for s in body.signals]
    db.add(chart)
    await db.commit()
    return await _get_chart_with_signals(db, chart.id)


@router.patch("/charts/{chart_id}", response_model=ChartRead)
async def update_chart(chart_id: str, body: ChartUpdate, db: AsyncSession = Depends(get_db)):
    chart = await db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    updates = body.model_dump(exclude_unset=True, exclude={"signals"})
    for field, value in updates.items():
        setattr(chart, field, value)

    if body.signals is not None:
        chart.signals.clear()
        await db.flush()
        chart.signals = [ChartSignal(chart_id=chart_id, **s.model_dump()) for s in body.signals]

    await db.commit()
    return await _get_chart_with_signals(db, chart_id)


@router.delete("/charts/{chart_id}", status_code=204)
async def delete_chart(chart_id: str, db: AsyncSession = Depends(get_db)):
    chart = await db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    await db.delete(chart)
    await db.commit()


async def _get_chart_with_signals(db: AsyncSession, chart_id: str) -> Chart:
    result = await db.execute(
        select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals))
    )
    return result.scalar_one()
```

- [ ] **Step 4: Wire it into `app/main.py`**

```python
# add near the top:
from app.routers import charts

# add after app.include_router(dashboards.router):
app.include_router(charts.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard pytest tests/test_charts_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add UNS_DASHBOARD/backend/app/routers/charts.py UNS_DASHBOARD/backend/app/main.py UNS_DASHBOARD/backend/tests/test_charts_router.py
git commit -m "feat(uns-dashboard): charts CRUD with signal replace-on-update"
```

---

## Task 5: Bridge — topic filtering + Redis stream writer (pure logic)

**Files:**
- Create: `UNS_DASHBOARD/bridge/app/filter.py`
- Create: `UNS_DASHBOARD/bridge/app/stream_writer.py`
- Create: `UNS_DASHBOARD/bridge/requirements.txt`
- Test: `UNS_DASHBOARD/bridge/tests/test_filter.py`
- Test: `UNS_DASHBOARD/bridge/tests/test_stream_writer.py`

**Interfaces:**
- Produces: `is_informative_topic(topic: str) -> bool`; `stream_key(topic: str) -> str`; `build_fields(payload: dict, arrival_iso: str) -> dict[str, str]` (flattened string fields for `XADD`, since Redis Streams only accept string/bytes field values).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_DASHBOARD/bridge/tests/test_filter.py
from app.filter import is_informative_topic


def test_informative_suffix_matches():
    assert is_informative_topic("Enterprise/Site/Area/_informative") is True


def test_descriptive_suffix_does_not_match():
    assert is_informative_topic("Enterprise/Site/Area/_descriptive") is False


def test_topic_without_suffix_does_not_match():
    assert is_informative_topic("Enterprise/Site/Area") is False
```

```python
# UNS_DASHBOARD/bridge/tests/test_stream_writer.py
import json

from app.stream_writer import build_fields, stream_key


def test_stream_key_prefixes_topic():
    assert stream_key("a/b/_informative") == "live:a/b/_informative"


def test_build_fields_serializes_payload_as_json_string():
    fields = build_fields({"Gen_RPM_Avg": 1342.1}, "2026-09-03T10:00:00+00:00")
    assert fields["time"] == "2026-09-03T10:00:00+00:00"
    assert json.loads(fields["payload"]) == {"Gen_RPM_Avg": 1342.1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd UNS_DASHBOARD/bridge && pytest tests/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write `app/filter.py`**

```python
def is_informative_topic(topic: str) -> bool:
    return topic.rsplit("/", 1)[-1] == "_informative"
```

- [ ] **Step 4: Write `app/stream_writer.py`**

```python
import json
from typing import Any


def stream_key(topic: str) -> str:
    return f"live:{topic}"


def build_fields(payload: dict[str, Any], arrival_iso: str) -> dict[str, str]:
    return {"time": arrival_iso, "payload": json.dumps(payload, ensure_ascii=False, default=str)}
```

- [ ] **Step 5: Write `requirements.txt`**

```
paho-mqtt==2.1.0
redis==5.2.1
pytest==8.3.3
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd UNS_DASHBOARD/bridge && pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add UNS_DASHBOARD/bridge/app/filter.py UNS_DASHBOARD/bridge/app/stream_writer.py UNS_DASHBOARD/bridge/requirements.txt UNS_DASHBOARD/bridge/tests
git commit -m "feat(uns-dashboard): bridge topic filtering and stream field encoding"
```

---

## Task 6: Bridge — MQTT wiring and entrypoint

**Files:**
- Create: `UNS_DASHBOARD/bridge/app/config.py`
- Create: `UNS_DASHBOARD/bridge/app/main.py`
- Create: `UNS_DASHBOARD/bridge/Dockerfile`

**Interfaces:**
- Consumes: `is_informative_topic`, `stream_key`, `build_fields` (Task 5).
- Produces: a running background worker; no importable interface consumed by later tasks (the backend only agrees with this service on the `stream_key`/field-shape convention, already covered by Task 5's tests).

- [ ] **Step 1: Write `app/config.py`**

```python
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    emqx_host: str
    emqx_port: int
    redis_host: str
    redis_port: int
    stream_maxlen: int
    mqtt_client_id: str


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        emqx_host=e.get("EMQX_HOST", "emqx"),
        emqx_port=int(e.get("EMQX_PORT", "1883")),
        redis_host=e.get("REDIS_HOST", "redis"),
        redis_port=int(e.get("REDIS_PORT", "6379")),
        stream_maxlen=int(e.get("STREAM_MAXLEN", "1000")),
        mqtt_client_id=e.get("MQTT_CLIENT_ID", "uns-dashboard-bridge"),
    )
```

- [ ] **Step 2: Write `app/main.py`**

```python
"""Entrypoint: subscribes to EMQX with a persistent session, filters
`_informative` topics, and XADDs each reading to its per-topic Redis Stream.

See docs/superpowers/specs/2026-09-03-uns-dashboard-design.md, Section 3.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import redis

from app.config import load_settings
from app.filter import is_informative_topic
from app.stream_writer import build_fields, stream_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("uns_dashboard.bridge")


def main() -> None:
    settings = load_settings()
    redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)

    def on_connect(client, userdata, connect_flags, reason_code, properties):
        logger.info("Connected to EMQX (reason_code=%s)", reason_code)
        client.subscribe("#", qos=1)

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from EMQX (reason_code=%s)", reason_code)

    def on_message(client, userdata, message):
        if not is_informative_topic(message.topic):
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Skipping non-JSON payload on %s", message.topic)
            return
        arrival_iso = datetime.now(timezone.utc).isoformat()
        fields = build_fields(payload, arrival_iso)
        try:
            redis_client.xadd(stream_key(message.topic), fields, maxlen=settings.stream_maxlen, approximate=True)
        except redis.RedisError:
            logger.exception("Failed to XADD reading for %s", message.topic)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        protocol=mqtt.MQTTv5,
        clean_session=False,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.connect(settings.emqx_host, settings.emqx_port, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests

CMD ["python", "-m", "app.main"]
```

- [ ] **Step 4: Manual verification (documented, no live broker in CI)**

Run: `docker compose up -d --build bridge redis` (after Task 12 wires `docker-compose.yml`), then `mosquitto_pub -h localhost -p 1883 -t 'test/_informative' -m '{"value": 1}'` and `redis-cli XRANGE live:test/_informative - +`.
Expected: one stream entry with `payload={"value": 1}`.

- [ ] **Step 5: Commit**

```bash
git add UNS_DASHBOARD/bridge/app/config.py UNS_DASHBOARD/bridge/app/main.py UNS_DASHBOARD/bridge/Dockerfile
git commit -m "feat(uns-dashboard): bridge MQTT-to-Redis-Stream wiring"
```

---

## Task 7: Historical query — pure range/bucket math

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/historian_query.py`
- Test: `UNS_DASHBOARD/backend/tests/test_historian_query.py`

**Interfaces:**
- Produces: `choose_bucket_seconds(range_seconds: float) -> int`; `resolve_relative_range(rule: str, now: datetime) -> tuple[datetime, datetime]`; `RELATIVE_RULES: dict[str, timedelta]`.

- [ ] **Step 1: Write the failing test (range/bucket portion)**

```python
# UNS_DASHBOARD/backend/tests/test_historian_query.py
from datetime import datetime, timedelta, timezone

from app.services.historian_query import choose_bucket_seconds, resolve_relative_range

NOW = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)


def test_choose_bucket_seconds_for_one_hour_range():
    assert choose_bucket_seconds(3600) == 5


def test_choose_bucket_seconds_for_one_month_range():
    assert choose_bucket_seconds(30 * 86400) == 3600


def test_resolve_relative_range_1h():
    start, end = resolve_relative_range("1h", NOW)
    assert end == NOW
    assert start == NOW - timedelta(hours=1)


def test_resolve_relative_range_30d():
    start, end = resolve_relative_range("30d", NOW)
    assert start == NOW - timedelta(days=30)


def test_resolve_relative_range_unknown_rule_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_relative_range("banana", NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_historian_query.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.historian_query'`

- [ ] **Step 3: Write the range/bucket portion of `app/services/historian_query.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta

_BUCKET_STEPS_SECONDS = [1, 5, 30, 60, 300, 3600, 86400]

RELATIVE_RULES: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def choose_bucket_seconds(range_seconds: float) -> int:
    """Target ~750 points across the range, snapped up to the next
    supported TimescaleDB bucket width."""
    target = range_seconds / 750
    for step in _BUCKET_STEPS_SECONDS:
        if step >= target:
            return step
    return _BUCKET_STEPS_SECONDS[-1]


def resolve_relative_range(rule: str, now: datetime) -> tuple[datetime, datetime]:
    if rule not in RELATIVE_RULES:
        raise ValueError(f"Unknown relative rule: {rule!r}")
    return now - RELATIVE_RULES[rule], now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_historian_query.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add UNS_DASHBOARD/backend/app/services/historian_query.py UNS_DASHBOARD/backend/tests/test_historian_query.py
git commit -m "feat(uns-dashboard): historical range resolution and bucket sizing"
```

---

## Task 8: Historical query — Timescale query + multi-topic merge

**Files:**
- Modify: `UNS_DASHBOARD/backend/app/services/historian_query.py`
- Modify: `UNS_DASHBOARD/backend/tests/test_historian_query.py`

**Interfaces:**
- Consumes: `choose_bucket_seconds` (this task, Task 7), `get_historian_db` (Task 1).
- Produces: `async def query_history(session: AsyncSession, signals: list[tuple[str, str]], start: datetime, end: datetime) -> list[dict]` — `signals` is `[(topic, signal_key), ...]`; returns `[{"time": iso_str, "<signal_key>": float | None, ...}, ...]` sorted by time, one row per bucket, merged across topics.

- [ ] **Step 1: Write the failing test (append to the same file)**

```python
# append to UNS_DASHBOARD/backend/tests/test_historian_query.py
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.services.historian_query import query_history

HISTORIAN_DATABASE_URL = os.environ.get("HISTORIAN_DATABASE_URL")

pytestmark_db = pytest.mark.skipif(
    not HISTORIAN_DATABASE_URL,
    reason="HISTORIAN_DATABASE_URL not set; requires a live UNS_HISTORIAN Postgres",
)


@pytest.fixture
async def historian_session():
    engine = create_async_engine(HISTORIAN_DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as s:
        await s.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'"))
        await s.commit()
        yield s
        await s.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'"))
        await s.commit()
    await engine.dispose()


@pytestmark_db
@pytest.mark.asyncio
async def test_query_history_merges_two_topics_by_bucket(historian_session: AsyncSession):
    from datetime import datetime, timezone
    t0 = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 3, 10, 0, 2, tzinfo=timezone.utc)
    await historian_session.execute(
        text(
            "INSERT INTO mqtt_messages (time, topic, payload, qos, retain) VALUES "
            "(:t0, 'pytest/site/_informative', '{\"Amb_Temp_Avg\": 19}', 1, false), "
            "(:t1, 'pytest/gen/_informative', '{\"Gen_Bear_Temp_Avg\": 58}', 1, false)"
        ),
        {"t0": t0, "t1": t1},
    )
    await historian_session.commit()

    rows = await query_history(
        historian_session,
        signals=[("pytest/site/_informative", "Amb_Temp_Avg"), ("pytest/gen/_informative", "Gen_Bear_Temp_Avg")],
        start=t0,
        end=t1,
    )
    assert len(rows) >= 1
    merged = {k: v for row in rows for k, v in row.items() if k != "time"}
    assert merged.get("Amb_Temp_Avg") == 19
    assert merged.get("Gen_Bear_Temp_Avg") == 58
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && HISTORIAN_DATABASE_URL=postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian pytest tests/test_historian_query.py -v`
Expected: FAIL — `ImportError: cannot import name 'query_history'`

- [ ] **Step 3: Append `query_history` to `app/services/historian_query.py`**

```python
# append to app/services/historian_query.py
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def query_history(
    session: AsyncSession,
    signals: list[tuple[str, str]],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Query one bucketed average per (topic, signal_key), grouping signals
    by topic to issue one query per unique topic, then merge all results by
    bucket timestamp into a single list of rows."""
    bucket_seconds = choose_bucket_seconds((end - start).total_seconds())
    by_topic: dict[str, list[str]] = defaultdict(list)
    for topic, key in signals:
        by_topic[topic].append(key)

    merged: dict[str, dict] = {}
    for topic, keys in by_topic.items():
        select_cols = ", ".join(f"avg((payload ->> :k{i})::numeric) AS v{i}" for i in range(len(keys)))
        params = {f"k{i}": key for i, key in enumerate(keys)}
        params.update({"topic": topic, "start": start, "end": end, "bucket": f"{bucket_seconds} seconds"})
        query = text(
            f"SELECT time_bucket(CAST(:bucket AS interval), time) AS bucket, {select_cols} "
            "FROM mqtt_messages WHERE topic = :topic AND time BETWEEN :start AND :end "
            "GROUP BY bucket ORDER BY bucket"
        )
        result = await session.execute(query, params)
        for row in result.mappings():
            bucket_iso = row["bucket"].isoformat()
            entry = merged.setdefault(bucket_iso, {"time": bucket_iso})
            for i, key in enumerate(keys):
                value = row[f"v{i}"]
                entry[key] = float(value) if value is not None else None

    return [merged[k] for k in sorted(merged)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && HISTORIAN_DATABASE_URL=postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian pytest tests/test_historian_query.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add UNS_DASHBOARD/backend/app/services/historian_query.py UNS_DASHBOARD/backend/tests/test_historian_query.py
git commit -m "feat(uns-dashboard): multi-topic historical query with time_bucket downsampling"
```

---

## Task 9: History router

**Files:**
- Create: `UNS_DASHBOARD/backend/app/routers/history.py`
- Modify: `UNS_DASHBOARD/backend/app/main.py`
- Test: `UNS_DASHBOARD/backend/tests/test_history_router.py`

**Interfaces:**
- Consumes: `query_history`, `resolve_relative_range` (Tasks 7-8); `Chart`, `ChartSignal` models (Task 2); `get_db`, `get_historian_db` (Task 1).
- Produces: `GET /charts/{chart_id}/history` → `{"points": [{"time": ..., "<signal_key>": ...}, ...]}`. Uses the chart's own stored `historical_range_type`/`historical_from`/`historical_to`/`historical_relative_rule` — the client never supplies a range, only the chart id, so `relative` rules are always resolved server-side against the server's clock.

- [ ] **Step 1: Write the failing test**

```python
# UNS_DASHBOARD/backend/tests/test_history_router.py
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

DATABASE_URL = os.environ.get("DATABASE_URL")
HISTORIAN_DATABASE_URL = os.environ.get("HISTORIAN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and HISTORIAN_DATABASE_URL),
    reason="DATABASE_URL and HISTORIAN_DATABASE_URL required; requires both live Postgres instances",
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_history_endpoint_returns_points_for_relative_chart(client: TestClient):
    dashboard = client.post("/dashboards/", json={"name": "pytest History"}).json()
    chart = client.post(
        f"/dashboards/{dashboard['id']}/charts/",
        json={
            "name": "Temp",
            "chart_type": "timeseries",
            "data_mode": "historical",
            "historical_range_type": "relative",
            "historical_relative_rule": "24h",
            "layout_x": 0, "layout_y": 0, "layout_w": 12, "layout_h": 4,
            "signals": [{"topic": "pytest/site/_informative", "signal_key": "Amb_Temp_Avg"}],
        },
    ).json()

    response = client.get(f"/charts/{chart['id']}/history")
    assert response.status_code == 200
    assert "points" in response.json()

    client.delete(f"/dashboards/{dashboard['id']}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=... HISTORIAN_DATABASE_URL=... pytest tests/test_history_router.py -v`
Expected: FAIL — 404 (router not mounted)

- [ ] **Step 3: Write `app/routers/history.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.database import get_db, get_historian_db
from app.models.dashboard import Chart
from app.services.historian_query import query_history, resolve_relative_range

router = APIRouter(tags=["history"])


@router.get("/charts/{chart_id}/history")
async def get_chart_history(
    chart_id: str,
    db: AsyncSession = Depends(get_db),
    historian_db: AsyncSession = Depends(get_historian_db),
):
    result = await db.execute(
        select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals))
    )
    chart = result.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    if chart.data_mode != "historical":
        raise HTTPException(status_code=400, detail="Chart is not in historical data_mode")

    if chart.historical_range_type == "relative":
        start, end = resolve_relative_range(chart.historical_relative_rule, datetime.now(timezone.utc))
    elif chart.historical_range_type == "fixed":
        start, end = chart.historical_from, chart.historical_to
    else:
        raise HTTPException(status_code=400, detail="Chart has no historical range configured")

    signals = [(s.topic, s.signal_key) for s in chart.signals]
    points = await query_history(historian_db, signals, start, end)
    return {"points": points}
```

- [ ] **Step 4: Wire it into `app/main.py`**

```python
# add near the top:
from app.routers import history

# add after app.include_router(charts.router):
app.include_router(history.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=... HISTORIAN_DATABASE_URL=... pytest tests/test_history_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add UNS_DASHBOARD/backend/app/routers/history.py UNS_DASHBOARD/backend/app/main.py UNS_DASHBOARD/backend/tests/test_history_router.py
git commit -m "feat(uns-dashboard): chart history endpoint with server-resolved relative ranges"
```

---

## Task 10: Signal catalog + descriptive prefill lookup

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/descriptive_lookup.py`
- Create: `UNS_DASHBOARD/backend/app/routers/signals.py`
- Modify: `UNS_DASHBOARD/backend/app/main.py`
- Test: `UNS_DASHBOARD/backend/tests/test_descriptive_lookup.py`
- Test: `UNS_DASHBOARD/backend/tests/test_signals_router.py`

**Interfaces:**
- Produces: `async def get_descriptive_signal_meta(topic_prefix: str, signal_key: str) -> dict | None` (returns `{"unit": ..., "min": ..., "max": ...}` or `None`); `GET /signals/catalog?topic_prefix=`; `GET /signals/descriptive?topic_prefix=&signal_key=`.

- [ ] **Step 1: Write the failing test for the lookup**

```python
# UNS_DASHBOARD/backend/tests/test_descriptive_lookup.py
import json

import httpx
import pytest

from app.services.descriptive_lookup import get_descriptive_signal_meta


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


@pytest.mark.asyncio
async def test_returns_unit_and_range_when_signals_map_has_the_key(monkeypatch):
    descriptive = {"signals": {"Amb_Temp_Avg": {"unit": "°C", "range": [-20, 120]}}}

    async def fake_get(self, url, **kwargs):
        return _FakeResponse(200, {"payload": json.dumps(descriptive)})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    meta = await get_descriptive_signal_meta("a/b", "Amb_Temp_Avg")
    assert meta == {"unit": "°C", "min": -20, "max": 120}


@pytest.mark.asyncio
async def test_returns_none_when_signal_not_in_descriptive_map(monkeypatch):
    descriptive = {"signals": {}}

    async def fake_get(self, url, **kwargs):
        return _FakeResponse(200, {"payload": json.dumps(descriptive)})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    assert await get_descriptive_signal_meta("a/b", "Missing_Key") is None


@pytest.mark.asyncio
async def test_returns_none_on_404():
    async def fake_get(self, url, **kwargs):
        return _FakeResponse(404, {})

    import httpx as httpx_module
    orig = httpx_module.AsyncClient.get
    httpx_module.AsyncClient.get = fake_get
    try:
        assert await get_descriptive_signal_meta("a/b", "Amb_Temp_Avg") is None
    finally:
        httpx_module.AsyncClient.get = orig
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_descriptive_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.descriptive_lookup'`

- [ ] **Step 3: Write `app/services/descriptive_lookup.py`**

```python
"""Best-effort lookup of a signal's unit/range from the retained _descriptive
MQTT message for its asset, via EMQX's retainer REST API. `_descriptive.signals`
is not a guaranteed project-wide schema (see design spec, Section 5) — any
shape mismatch or missing entry returns None rather than raising."""
from __future__ import annotations

import json
import urllib.parse

import httpx

from app.config import settings


def _api_base() -> str:
    return f"http://{settings.emqx_host}:{settings.emqx_api_port}/api/v5"


def _auth() -> tuple[str, str] | None:
    if settings.emqx_api_username:
        return (settings.emqx_api_username, settings.emqx_api_password or "")
    return None


async def get_descriptive_signal_meta(topic_prefix: str, signal_key: str) -> dict | None:
    topic = f"{topic_prefix}/_descriptive"
    try:
        encoded = urllib.parse.quote(topic, safe="")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{_api_base()}/retainer/message/{encoded}", auth=_auth())
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload_str = response.json().get("payload", "")
            if not payload_str:
                return None
            descriptive = json.loads(payload_str)
            entry = descriptive.get("signals", {}).get(signal_key)
            if not entry:
                return None
            rng = entry.get("range") or [None, None]
            return {"unit": entry.get("unit"), "min": rng[0], "max": rng[1]}
    except Exception:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_descriptive_lookup.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the signals router (needs `HISTORIAN_DATABASE_URL`)**

```python
# UNS_DASHBOARD/backend/tests/test_signals_router.py
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

HISTORIAN_DATABASE_URL = os.environ.get("HISTORIAN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not HISTORIAN_DATABASE_URL, reason="HISTORIAN_DATABASE_URL not set; requires a live UNS_HISTORIAN Postgres"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_catalog_lists_topics_and_keys_under_prefix(client: TestClient):
    from sqlalchemy import create_engine, text

    engine = create_engine(HISTORIAN_DATABASE_URL.replace("+asyncpg", ""))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_catalog/%'"))
        conn.execute(
            text(
                "INSERT INTO mqtt_messages (time, topic, payload, qos, retain) VALUES "
                "(now(), 'pytest_catalog/gen/_informative', '{\"Gen_RPM_Avg\": 1300}', 1, false)"
            )
        )

    response = client.get("/signals/catalog", params={"topic_prefix": "pytest_catalog"})
    assert response.status_code == 200
    topics = response.json()
    assert any(t["topic"] == "pytest_catalog/gen/_informative" and "Gen_RPM_Avg" in t["keys"] for t in topics)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_catalog/%'"))
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && HISTORIAN_DATABASE_URL=... pytest tests/test_signals_router.py -v`
Expected: FAIL — 404 (router not mounted)

- [ ] **Step 7: Write `app/routers/signals.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_historian_db
from app.services.descriptive_lookup import get_descriptive_signal_meta

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/catalog")
async def signal_catalog(
    topic_prefix: str = Query(..., min_length=1),
    historian_db: AsyncSession = Depends(get_historian_db),
):
    topics_result = await historian_db.execute(
        text(
            "SELECT DISTINCT topic FROM mqtt_messages "
            "WHERE topic LIKE :prefix AND topic LIKE '%\\_informative' ESCAPE '\\' "
            "ORDER BY topic"
        ),
        {"prefix": f"{topic_prefix}%"},
    )
    topics = [row[0] for row in topics_result.fetchall()]

    catalog = []
    for topic in topics:
        latest = await historian_db.execute(
            text("SELECT payload FROM mqtt_messages WHERE topic = :topic ORDER BY time DESC LIMIT 1"),
            {"topic": topic},
        )
        row = latest.first()
        payload = row[0] if row else None
        keys = [k for k in (payload or {}).keys() if k != "timestamp"]
        catalog.append({"topic": topic, "keys": keys})
    return catalog


@router.get("/descriptive")
async def signal_descriptive(
    topic_prefix: str = Query(..., min_length=1),
    signal_key: str = Query(..., min_length=1),
):
    meta = await get_descriptive_signal_meta(topic_prefix, signal_key)
    return meta or {}
```

- [ ] **Step 8: Wire it into `app/main.py`**

```python
# add near the top:
from app.routers import signals

# add after app.include_router(history.router):
app.include_router(signals.router)
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && HISTORIAN_DATABASE_URL=... pytest tests/test_signals_router.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add UNS_DASHBOARD/backend/app/services/descriptive_lookup.py UNS_DASHBOARD/backend/app/routers/signals.py UNS_DASHBOARD/backend/app/main.py UNS_DASHBOARD/backend/tests/test_descriptive_lookup.py UNS_DASHBOARD/backend/tests/test_signals_router.py
git commit -m "feat(uns-dashboard): signal catalog and best-effort descriptive prefill"
```

---

## Task 11: WebSocket fan-out (TopicHub, pure logic) + stream route

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/ws_manager.py`
- Create: `UNS_DASHBOARD/backend/app/routers/stream.py`
- Modify: `UNS_DASHBOARD/backend/app/main.py`
- Test: `UNS_DASHBOARD/backend/tests/test_ws_manager.py`

**Interfaces:**
- Produces: `class TopicHub` with `subscribe(client_id: str, topic: str) -> None`, `unsubscribe_all(client_id: str) -> None`, `subscribers_for(topic: str) -> set[str]`, `topics() -> set[str]` — pure bookkeeping, no I/O. `WebSocket /ws/dashboards/{dashboard_id}` route uses it plus a Redis `XREAD` reader task per topic (I/O glue, not unit tested — manual verification, per Global Constraints).

- [ ] **Step 1: Write the failing test**

```python
# UNS_DASHBOARD/backend/tests/test_ws_manager.py
from app.services.ws_manager import TopicHub


def test_subscribe_tracks_client_under_topic():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.subscribe("client-2", "a/_informative")
    assert hub.subscribers_for("a/_informative") == {"client-1", "client-2"}


def test_topics_reflects_all_actively_subscribed_topics():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.subscribe("client-1", "b/_informative")
    assert hub.topics() == {"a/_informative", "b/_informative"}


def test_unsubscribe_all_removes_client_from_every_topic():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.subscribe("client-2", "a/_informative")
    hub.unsubscribe_all("client-1")
    assert hub.subscribers_for("a/_informative") == {"client-2"}


def test_unsubscribe_all_drops_topic_entirely_once_empty():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.unsubscribe_all("client-1")
    assert "a/_informative" not in hub.topics()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_ws_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ws_manager'`

- [ ] **Step 3: Write the `TopicHub` portion of `app/services/ws_manager.py`**

```python
"""Pure subscription bookkeeping (TopicHub) plus the WebSocket/Redis async
glue that uses it. TopicHub has no I/O and is fully unit tested; the reader
loop is verified manually (see design spec, testing philosophy)."""
from __future__ import annotations

from collections import defaultdict


class TopicHub:
    def __init__(self) -> None:
        self._topic_to_clients: dict[str, set[str]] = defaultdict(set)
        self._client_to_topics: dict[str, set[str]] = defaultdict(set)

    def subscribe(self, client_id: str, topic: str) -> None:
        self._topic_to_clients[topic].add(client_id)
        self._client_to_topics[client_id].add(topic)

    def unsubscribe_all(self, client_id: str) -> None:
        for topic in self._client_to_topics.pop(client_id, set()):
            clients = self._topic_to_clients.get(topic)
            if clients:
                clients.discard(client_id)
                if not clients:
                    del self._topic_to_clients[topic]

    def subscribers_for(self, topic: str) -> set[str]:
        return set(self._topic_to_clients.get(topic, set()))

    def topics(self) -> set[str]:
        return set(self._topic_to_clients.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/backend && pytest tests/test_ws_manager.py -v`
Expected: PASS

- [ ] **Step 5: Append the WebSocket connection registry and Redis reader loop to `app/services/ws_manager.py`**

```python
# append to app/services/ws_manager.py
import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger("uns_dashboard.ws_manager")

hub = TopicHub()
_connections: dict[str, WebSocket] = {}
_reader_tasks: dict[str, asyncio.Task] = {}


async def register(client_id: str, websocket: WebSocket) -> None:
    _connections[client_id] = websocket


async def unregister(client_id: str) -> None:
    hub.unsubscribe_all(client_id)
    _connections.pop(client_id, None)
    for topic in list(_reader_tasks):
        if not hub.subscribers_for(topic):
            _reader_tasks.pop(topic).cancel()


def _stream_key(topic: str) -> str:
    return f"live:{topic}"


async def _read_topic_forever(topic: str) -> None:
    redis_client = aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    last_id = "$"
    try:
        while hub.subscribers_for(topic):
            response = await redis_client.xread({_stream_key(topic): last_id}, block=5000, count=10)
            for _stream, entries in response or []:
                for entry_id, fields in entries:
                    last_id = entry_id
                    frame = {"topic": topic, "time": fields.get("time"), "payload": json.loads(fields.get("payload", "{}"))}
                    for client_id in hub.subscribers_for(topic):
                        ws = _connections.get(client_id)
                        if ws is not None:
                            try:
                                await ws.send_json(frame)
                            except Exception:
                                logger.warning("Failed to send frame to client %s", client_id)
    finally:
        await redis_client.aclose()


def ensure_reader(topic: str) -> None:
    if topic not in _reader_tasks or _reader_tasks[topic].done():
        _reader_tasks[topic] = asyncio.create_task(_read_topic_forever(topic))
```

- [ ] **Step 6: Write `app/routers/stream.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services import ws_manager

router = APIRouter(tags=["stream"])


@router.websocket("/ws/dashboards/{dashboard_id}")
async def dashboard_stream(websocket: WebSocket, dashboard_id: str):
    await websocket.accept()
    client_id = f"{dashboard_id}:{id(websocket)}"
    await ws_manager.register(client_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            for topic in message.get("subscribe", []):
                ws_manager.hub.subscribe(client_id, topic)
                ws_manager.ensure_reader(topic)
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.unregister(client_id)
```

- [ ] **Step 7: Wire it into `app/main.py`**

```python
# add near the top:
from app.routers import stream

# add after app.include_router(signals.router):
app.include_router(stream.router)
```

- [ ] **Step 8: Manual verification (documented, no live broker/Redis in CI)**

Run: `docker compose up -d --build` (Task 12), open a WS client to `ws://localhost:<port>/ws/dashboards/test`, send `{"subscribe": ["test/_informative"]}`, then `mosquitto_pub` a reading on that topic and confirm the frame arrives.

- [ ] **Step 9: Commit**

```bash
git add UNS_DASHBOARD/backend/app/services/ws_manager.py UNS_DASHBOARD/backend/app/routers/stream.py UNS_DASHBOARD/backend/app/main.py UNS_DASHBOARD/backend/tests/test_ws_manager.py
git commit -m "feat(uns-dashboard): WebSocket fan-out over per-topic Redis stream readers"
```

---

## Task 12: Docker Compose wiring (all 5 services + cross-stack changes)

**Files:**
- Create: `UNS_DASHBOARD/docker-compose.yml`
- Create: `UNS_DASHBOARD/.env.example`
- Create: `UNS_DASHBOARD/.gitignore`
- Create: `UNS_DASHBOARD/scripts/up.sh`, `down.sh`, `restart.sh`, `logs.sh`, `status.sh`
- Create: `UNS_DASHBOARD/postgres/init.sql`
- Modify: `UNS_HISTORIAN/docker-compose.yml`
- Modify: `docker-compose.yml` (root)

**Interfaces:**
- Produces: five running containers (`uns_dashboard_postgres`, `uns_dashboard_redis`, `uns_dashboard_bridge`, `uns_dashboard_backend`, `uns_dashboard_frontend` — frontend container added in Task 14) reachable from the root compose project; `uns_historian_postgres` additionally reachable by DNS name from `uns_dashboard_backend`.

- [ ] **Step 1: Write `postgres/init.sql`**

```sql
-- UNS_DASHBOARD/postgres/init.sql
-- Tables are created by the backend's SQLAlchemy metadata on startup
-- (see app/database.py: create_tables). This file exists so the
-- docker-compose volume mount point is documented and ready if a raw-SQL
-- migration is ever needed later.
```

- [ ] **Step 2: Write `UNS_DASHBOARD/docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: uns_dashboard_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-dashboard}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-dashboardpassword}
      POSTGRES_DB: ${POSTGRES_DB:-uns_dashboard}
    volumes:
      - dashboard_postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "${POSTGRES_PORT:-5435}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-dashboard} -d ${POSTGRES_DB:-uns_dashboard}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - dashboard_net

  redis:
    image: redis:7-alpine
    container_name: uns_dashboard_redis
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - dashboard_net

  bridge:
    build:
      context: ./bridge
      dockerfile: Dockerfile
    container_name: uns_dashboard_bridge
    init: true
    environment:
      EMQX_HOST: ${EMQX_HOST:-emqx}
      EMQX_PORT: ${EMQX_PORT:-1883}
      REDIS_HOST: ${REDIS_HOST:-redis}
      REDIS_PORT: ${REDIS_PORT:-6379}
      STREAM_MAXLEN: ${STREAM_MAXLEN:-1000}
      MQTT_CLIENT_ID: ${BRIDGE_MQTT_CLIENT_ID:-uns-dashboard-bridge}
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - dashboard_net
      - uns_manager_net
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: uns_dashboard_backend
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql+asyncpg://${POSTGRES_USER:-dashboard}:${POSTGRES_PASSWORD:-dashboardpassword}@uns_dashboard_postgres:5432/${POSTGRES_DB:-uns_dashboard}}
      HISTORIAN_DATABASE_URL: ${HISTORIAN_DATABASE_URL:-postgresql+asyncpg://historian:historianpassword@uns_historian_postgres:5432/uns_historian}
      EMQX_HOST: ${EMQX_HOST:-emqx}
      EMQX_PORT: ${EMQX_PORT:-1883}
      EMQX_API_PORT: ${EMQX_API_PORT:-18083}
      REDIS_HOST: ${REDIS_HOST:-redis}
      REDIS_PORT: ${REDIS_PORT:-6379}
      STREAM_MAXLEN: ${STREAM_MAXLEN:-1000}
    ports:
      - "${BACKEND_PORT:-8001}:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - dashboard_net
      - uns_manager_net
    restart: unless-stopped

volumes:
  dashboard_postgres_data:
    name: uns_dashboard_dashboard_postgres_data

networks:
  dashboard_net:
    driver: bridge
    name: uns_dashboard_dashboard_net
  uns_manager_net:
    external: true
    name: ${UNS_MANAGER_NETWORK_NAME:-uns_manager_uns_net}
```

(The `frontend` service is added in Task 14, once its Dockerfile exists.)

- [ ] **Step 3: Write `.env.example`**

```
POSTGRES_USER=dashboard
POSTGRES_PASSWORD=dashboardpassword
POSTGRES_DB=uns_dashboard
POSTGRES_PORT=5435
EMQX_HOST=emqx
EMQX_PORT=1883
EMQX_API_PORT=18083
EMQX_API_USERNAME=
EMQX_API_PASSWORD=
REDIS_HOST=redis
REDIS_PORT=6379
STREAM_MAXLEN=1000
HISTORIAN_DATABASE_URL=postgresql+asyncpg://historian:historianpassword@uns_historian_postgres:5432/uns_historian
BACKEND_PORT=8001
VITE_API_BASE_URL=http://localhost:8001
UNS_MANAGER_NETWORK_NAME=uns_manager_uns_net
```

- [ ] **Step 4: Write `.gitignore`**

```
.env
node_modules/
__pycache__/
*.pyc
.pytest_cache/
dist/
```

- [ ] **Step 5: Write the ops scripts**

```bash
#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/up.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build
echo "UNS Dashboard is starting. Use scripts/status.sh to check container health."
```

```bash
#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/down.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
```

```bash
#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/restart.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose restart "$@"
```

```bash
#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/logs.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose logs -f "$@"
```

```bash
#!/usr/bin/env bash
# UNS_DASHBOARD/scripts/status.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
```

Run: `chmod +x UNS_DASHBOARD/scripts/*.sh`

- [ ] **Step 6: Modify `UNS_HISTORIAN/docker-compose.yml`** — add `uns_manager_net` to `historian_postgres`'s `networks:` list (find the `historian_postgres` service block and change its `networks:` from `- historian_net` to include the second network):

```yaml
    networks:
      - historian_net
      - uns_manager_net
```

- [ ] **Step 7: Modify root `docker-compose.yml`** — add the include entry and update the header comment:

```yaml
include:
  - UNS_MANAGER/docker-compose.yml
  - UNS_HISTORIAN/docker-compose.yml
  - UNS_DASHBOARD/docker-compose.yml
```

- [ ] **Step 8: Verify the compose files are valid**

Run: `cd "G:/00_data/00_Formacion/INARI_V05" && docker compose config --quiet`
Expected: no output, exit code 0 (validates YAML + variable interpolation across all three included files)

- [ ] **Step 9: Bring the new stack up standalone and confirm health**

Run: `cd UNS_DASHBOARD && cp .env.example .env && ../UNS_MANAGER && docker compose up -d && cd ../UNS_DASHBOARD && ./scripts/up.sh && ./scripts/status.sh`
Expected: `uns_dashboard_postgres`, `uns_dashboard_redis` show `healthy`; `uns_dashboard_backend` shows `running`. Then `curl http://localhost:8001/health` returns `{"status":"ok"}`.

- [ ] **Step 10: Run the DB-gated backend tests now that Postgres is live**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard HISTORIAN_DATABASE_URL=postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian pytest tests/ -v`
Expected: all tests PASS (none skipped)

- [ ] **Step 11: Commit**

```bash
git add UNS_DASHBOARD/docker-compose.yml UNS_DASHBOARD/.env.example UNS_DASHBOARD/.gitignore UNS_DASHBOARD/scripts UNS_DASHBOARD/postgres/init.sql UNS_HISTORIAN/docker-compose.yml docker-compose.yml
git commit -m "feat(uns-dashboard): docker-compose wiring, ops scripts, cross-stack network access to historian"
```

---

## Task 13: Frontend foundation (scaffold, tokens, API client, routing)

**Files:**
- Create: `UNS_DASHBOARD/frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`, `index.html`
- Create: `UNS_DASHBOARD/frontend/src/main.tsx`, `src/App.tsx`, `src/api/client.ts`, `src/types/dashboard.ts`
- Create: `UNS_DASHBOARD/frontend/Dockerfile`, `nginx.conf`
- Create: `UNS_DASHBOARD/frontend/vitest.config.ts`

**Interfaces:**
- Produces: `api` client object (`dashboards.list/get/create/update/delete/publish`, `charts.create/update/delete`, `signals.catalog/descriptive`, `history.get`); `Dashboard`, `Chart`, `ChartSignal` TS types; `<App>` with routes `/`, `/dashboards/:id/edit`, `/dashboards/:id`.

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "uns-dashboard-frontend",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "axios": "^1.7.9",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "react-grid-layout": "^1.4.4",
    "recharts": "^2.13.3"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@types/react-grid-layout": "^1.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.16",
    "typescript": "^5.7.2",
    "vite": "^6.0.3",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 2: Write `vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE_URL || "http://localhost:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
```

- [ ] **Step 3: Write `vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

- [ ] **Step 4: Write `tsconfig.json`** (identical to `UNS_MANAGER/frontend/tsconfig.json`)

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

- [ ] **Step 5: Write `tailwind.config.js`** (reuses `UNS_MANAGER/frontend`'s exact palette for visual consistency across the two apps)

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
      colors: {
        surface: { DEFAULT: '#FFFFFF', subtle: '#F7F8FA', muted: '#EEF1F4' },
        ink: { DEFAULT: '#171A1D', secondary: '#5E6872', muted: '#87919B' },
        border: { DEFAULT: '#DDE2E7', subtle: '#EDF0F3' },
        accent: { DEFAULT: '#198ACB', soft: '#E8F5FC' },
        success: { DEFAULT: '#17865D', soft: '#E7F5EF' },
        warning: { DEFAULT: '#A9630B', soft: '#FFF3DC' },
        danger: { DEFAULT: '#C43F3F', soft: '#FCEBEC' },
        code: { bg: '#111820', ink: '#DCE8F2', muted: '#687786' },
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 6: Write `postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 7: Write `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>UNS Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Write `src/types/dashboard.ts`**

```typescript
export interface ChartSignal {
  id?: string;
  topic: string;
  signal_key: string;
  label?: string | null;
  unit?: string | null;
  color?: string | null;
  min?: number | null;
  max?: number | null;
  source?: "auto" | "manual";
}

export type ChartType = "timeseries" | "gauge" | "kpi" | "bar" | "table" | "status";
export type DataMode = "live" | "historical";
export type HistoricalRangeType = "fixed" | "relative";
export type RelativeRule = "1h" | "24h" | "7d" | "30d";

export interface Chart {
  id: string;
  dashboard_id: string;
  name: string;
  description?: string | null;
  chart_type: ChartType;
  data_mode: DataMode;
  historical_range_type?: HistoricalRangeType | null;
  historical_from?: string | null;
  historical_to?: string | null;
  historical_relative_rule?: RelativeRule | null;
  layout_x: number;
  layout_y: number;
  layout_w: number;
  layout_h: number;
  color?: string | null;
  config?: Record<string, unknown> | null;
  signals: ChartSignal[];
}

export interface Dashboard {
  id: string;
  name: string;
  description?: string | null;
  status: "draft" | "published";
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardDetail extends Dashboard {
  charts: Chart[];
}

export interface HistoryPoint {
  time: string;
  [signalKey: string]: string | number | null;
}
```

- [ ] **Step 9: Write `src/api/client.ts`**

```typescript
import axios from "axios";
import type { Chart, Dashboard, DashboardDetail, HistoryPoint } from "../types/dashboard";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";
const http = axios.create({ baseURL: BASE });

export const api = {
  dashboards: {
    list: () => http.get<Dashboard[]>("/dashboards/").then((r) => r.data),
    get: (id: string) => http.get<DashboardDetail>(`/dashboards/${id}`).then((r) => r.data),
    create: (body: { name: string; description?: string }) =>
      http.post<Dashboard>("/dashboards/", body).then((r) => r.data),
    update: (id: string, body: Partial<{ name: string; description: string }>) =>
      http.patch<Dashboard>(`/dashboards/${id}`, body).then((r) => r.data),
    delete: (id: string) => http.delete(`/dashboards/${id}`),
    publish: (id: string) => http.post<Dashboard>(`/dashboards/${id}/publish`).then((r) => r.data),
  },
  charts: {
    create: (dashboardId: string, body: Omit<Chart, "id" | "dashboard_id">) =>
      http.post<Chart>(`/dashboards/${dashboardId}/charts/`, body).then((r) => r.data),
    update: (chartId: string, body: Partial<Omit<Chart, "id" | "dashboard_id">>) =>
      http.patch<Chart>(`/charts/${chartId}`, body).then((r) => r.data),
    delete: (chartId: string) => http.delete(`/charts/${chartId}`),
  },
  signals: {
    catalog: (topicPrefix: string) =>
      http.get<{ topic: string; keys: string[] }[]>("/signals/catalog", { params: { topic_prefix: topicPrefix } }).then((r) => r.data),
    descriptive: (topicPrefix: string, signalKey: string) =>
      http.get<{ unit?: string; min?: number; max?: number }>("/signals/descriptive", { params: { topic_prefix: topicPrefix, signal_key: signalKey } }).then((r) => r.data),
  },
  history: {
    get: (chartId: string) => http.get<{ points: HistoryPoint[] }>(`/charts/${chartId}/history`).then((r) => r.data),
  },
};

export function wsUrl(dashboardId: string): string {
  const wsBase = BASE.replace(/^http/, "ws");
  return `${wsBase}/ws/dashboards/${dashboardId}`;
}
```

- [ ] **Step 10: Write `src/App.tsx` and `src/main.tsx`** (pages are stubs filled in later tasks)

```tsx
// src/pages/MenuPage.tsx (stub, replaced in Task 15)
export function MenuPage() {
  return <div>Menu</div>;
}
```

```tsx
// src/pages/EditorPage.tsx (stub, replaced in Task 19)
export function EditorPage() {
  return <div>Editor</div>;
}
```

```tsx
// src/pages/ViewerPage.tsx (stub, replaced in Task 21)
export function ViewerPage() {
  return <div>Viewer</div>;
}
```

```tsx
// src/App.tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { MenuPage } from "./pages/MenuPage";
import { EditorPage } from "./pages/EditorPage";
import { ViewerPage } from "./pages/ViewerPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MenuPage />} />
        <Route path="/dashboards/:id/edit" element={<EditorPage />} />
        <Route path="/dashboards/:id" element={<ViewerPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

```tsx
// src/main.tsx
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

```css
/* src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 11: Write the Dockerfile and nginx.conf**

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
ARG VITE_API_BASE_URL=http://localhost:8001
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json .
RUN npm install

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

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

    location /ws/ {
        proxy_pass http://backend:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

- [ ] **Step 12: Install and verify the build compiles**

Run: `cd UNS_DASHBOARD/frontend && npm install && npm run build`
Expected: exits 0, `dist/` produced

- [ ] **Step 13: Add the frontend service to `UNS_DASHBOARD/docker-compose.yml`**

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:8001}
    container_name: uns_dashboard_frontend
    ports:
      - "${FRONTEND_PORT:-3002}:80"
    depends_on:
      - backend
    networks:
      - dashboard_net
    restart: unless-stopped
```

- [ ] **Step 14: Commit**

```bash
git add UNS_DASHBOARD/frontend UNS_DASHBOARD/docker-compose.yml
git commit -m "feat(uns-dashboard): frontend scaffold, API client, routing, docker service"
```

---

## Task 14: Menu page

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/pages/MenuPage.tsx` (replaces stub)

**Interfaces:**
- Consumes: `api.dashboards.*` (Task 13).
- Produces: `<MenuPage>` rendered at `/`.

- [ ] **Step 1: Write `src/pages/MenuPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard } from "../types/dashboard";

export function MenuPage() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const navigate = useNavigate();

  const load = () => {
    api.dashboards.list().then(setDashboards);
  };

  useEffect(load, []);

  const createDashboard = async () => {
    const name = window.prompt("Nombre del dashboard");
    if (!name) return;
    const created = await api.dashboards.create({ name });
    navigate(`/dashboards/${created.id}/edit`);
  };

  const deleteDashboard = async (id: string) => {
    if (!window.confirm("¿Eliminar este dashboard?")) return;
    await api.dashboards.delete(id);
    load();
  };

  return (
    <div className="min-h-screen bg-surface-subtle p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">SCADA Dashboards</h1>
          <p className="text-ink-secondary text-sm">Dashboard authoring and production publishing</p>
        </div>
        <button onClick={createDashboard} className="bg-accent text-white px-4 py-2 rounded-lg font-semibold">
          + Nuevo dashboard
        </button>
      </div>
      <div className="bg-surface rounded-xl border border-border p-6">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-muted text-xs uppercase border-b border-border">
              <th className="py-2">Nombre</th>
              <th>Descripción</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {dashboards.map((d) => (
              <tr key={d.id} className="border-b border-border-subtle">
                <td className="py-3 font-semibold text-ink">{d.name}</td>
                <td className="text-ink-secondary">{d.description}</td>
                <td>
                  <span className={d.status === "published" ? "text-success" : "text-warning"}>
                    {d.status === "published" ? "Publicado" : "Borrador"}
                  </span>
                </td>
                <td className="space-x-2">
                  <Link to={`/dashboards/${d.id}`} className="border border-border rounded px-3 py-1">Ver</Link>
                  <Link to={`/dashboards/${d.id}/edit`} className="border border-border rounded px-3 py-1">Editar</Link>
                  <button onClick={() => deleteDashboard(d.id)} className="bg-danger-soft text-danger rounded px-3 py-1">Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Manual verification**

Run: `cd UNS_DASHBOARD/frontend && npm run dev`, open `http://localhost:5174/`, create a dashboard, confirm it lists, edit link navigates, delete removes it.
Expected: all four actions work against the live backend from Task 12.

- [ ] **Step 3: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/pages/MenuPage.tsx
git commit -m "feat(uns-dashboard): menu page — list, create, edit, delete dashboards"
```

---

## Task 15: Shared chart shell + TimeSeriesChart + BarChart

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/components/ChartCardShell.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/charts/TimeSeriesChart.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/charts/BarChart.tsx`
- Test: `UNS_DASHBOARD/frontend/src/components/charts/__tests__/TimeSeriesChart.test.tsx`

**Interfaces:**
- Produces: `<ChartCardShell title, modeLabel, editable, onRemove?, children>`; `<TimeSeriesChart signals: ChartSignal[], points: HistoryPoint[]>`; `<BarChart signals: ChartSignal[], values: Record<string, number>>`. Both chart components are shared verbatim between Editor and Viewer — only `editable` on the shell differs.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/charts/__tests__/TimeSeriesChart.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TimeSeriesChart } from "../TimeSeriesChart";

describe("TimeSeriesChart", () => {
  it("renders a legend entry per signal", () => {
    render(
      <TimeSeriesChart
        signals={[{ topic: "a", signal_key: "Amb_Temp_Avg", label: "Amb Temp", color: "#3B82F6" }]}
        points={[{ time: "2026-09-03T10:00:00Z", Amb_Temp_Avg: 19 }]}
      />
    );
    expect(screen.getByText("Amb Temp")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/frontend && npx vitest run src/components/charts/__tests__/TimeSeriesChart.test.tsx`
Expected: FAIL — cannot find module `../TimeSeriesChart`

- [ ] **Step 3: Write `src/components/ChartCardShell.tsx`**

```tsx
import type { ReactNode } from "react";

export function ChartCardShell({
  title,
  modeLabel,
  editable,
  onRemove,
  children,
}: {
  title: string;
  modeLabel: string;
  editable: boolean;
  onRemove?: () => void;
  children: ReactNode;
}) {
  const isLive = modeLabel.startsWith("Live");
  return (
    <div className="h-full w-full bg-surface border border-border rounded-lg p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-bold text-ink">{title}</span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${isLive ? "bg-success-soft text-success" : "bg-accent-soft text-accent"}`}>
            {modeLabel}
          </span>
        </div>
        {editable && onRemove && (
          <button onClick={onRemove} className="text-ink-muted text-xs">✕</button>
        )}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}
```

- [ ] **Step 4: Write `src/components/charts/TimeSeriesChart.tsx`**

```tsx
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartSignal, HistoryPoint } from "../../types/dashboard";

export function TimeSeriesChart({ signals, points }: { signals: ChartSignal[]; points: HistoryPoint[] }) {
  return (
    <div className="h-full flex flex-col gap-2">
      <div className="flex gap-4">
        {signals.map((s) => (
          <div key={s.signal_key} className="flex items-center gap-1.5 text-xs text-ink-secondary">
            <span className="w-2.5 h-0.5 rounded" style={{ backgroundColor: s.color ?? "#3B82F6" }} />
            {s.label ?? s.signal_key}
          </div>
        ))}
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points}>
          <XAxis dataKey="time" hide />
          <YAxis width={32} tick={{ fontSize: 10 }} />
          <Tooltip />
          {signals.map((s) => (
            <Area
              key={s.signal_key}
              type="monotone"
              dataKey={s.signal_key}
              stroke={s.color ?? "#3B82F6"}
              fill={s.color ?? "#3B82F6"}
              fillOpacity={0.15}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 5: Write `src/components/charts/BarChart.tsx`**

```tsx
import type { ChartSignal } from "../../types/dashboard";

export function BarChart({ signals, values }: { signals: ChartSignal[]; values: Record<string, number> }) {
  const max = Math.max(1, ...signals.map((s) => values[s.signal_key] ?? 0));
  return (
    <div className="h-full flex items-end justify-center gap-8">
      {signals.map((s) => {
        const value = values[s.signal_key] ?? 0;
        return (
          <div key={s.signal_key} className="flex flex-col items-center gap-1.5">
            <span className="text-xs font-bold text-ink">{value}{s.unit}</span>
            <div
              className="w-10 rounded-t"
              style={{ height: `${(value / max) * 140}px`, backgroundColor: s.color ?? "#3B82F6" }}
            />
            <span className="text-xs text-ink-secondary">{s.label ?? s.signal_key}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/frontend && npx vitest run src/components/charts/__tests__/TimeSeriesChart.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/components/ChartCardShell.tsx UNS_DASHBOARD/frontend/src/components/charts/TimeSeriesChart.tsx UNS_DASHBOARD/frontend/src/components/charts/BarChart.tsx UNS_DASHBOARD/frontend/src/components/charts/__tests__/TimeSeriesChart.test.tsx
git commit -m "feat(uns-dashboard): chart card shell, time series and bar chart components"
```

---

## Task 16: Gauge, KPI, status, table chart components

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/components/charts/GaugeChart.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/charts/KpiTile.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/charts/StatusIndicator.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/charts/ValuesTable.tsx`
- Test: `UNS_DASHBOARD/frontend/src/components/charts/__tests__/GaugeChart.test.tsx`

**Interfaces:**
- Produces: `<GaugeChart signal: ChartSignal, value: number>`; `<KpiTile signal: ChartSignal, value: number>`; `<StatusIndicator states: {label: string, value: string, color: "success"|"warning"|"danger"}[]>`; `<ValuesTable signals: ChartSignal[], values: Record<string, {value: number, updatedAt: string}>>`.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/charts/__tests__/GaugeChart.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GaugeChart } from "../GaugeChart";

describe("GaugeChart", () => {
  it("renders the current value and signal label", () => {
    render(<GaugeChart signal={{ topic: "a", signal_key: "Amb_Temp_Avg", label: "Amb Temp", unit: "°C", min: -20, max: 120 }} value={19} />);
    expect(screen.getByText("19°C")).toBeInTheDocument();
    expect(screen.getByText("Amb Temp")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/frontend && npx vitest run src/components/charts/__tests__/GaugeChart.test.tsx`
Expected: FAIL — cannot find module `../GaugeChart`

- [ ] **Step 3: Write `src/components/charts/GaugeChart.tsx`**

```tsx
import type { ChartSignal } from "../../types/dashboard";

export function GaugeChart({ signal, value }: { signal: ChartSignal; value: number }) {
  const min = signal.min ?? 0;
  const max = signal.max ?? 100;
  const ratio = Math.min(1, Math.max(0, (value - min) / (max - min || 1)));
  const sweep = 270 * ratio;

  const arcPath = (startDeg: number, sweepDeg: number, r: number) => {
    const toRad = (d: number) => (d * Math.PI) / 180;
    const cx = 50, cy = 50;
    const x1 = cx + r * Math.cos(toRad(startDeg));
    const y1 = cy - r * Math.sin(toRad(startDeg));
    const endDeg = startDeg - sweepDeg;
    const x2 = cx + r * Math.cos(toRad(endDeg));
    const y2 = cy - r * Math.sin(toRad(endDeg));
    const largeArc = sweepDeg > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <svg viewBox="0 0 100 100" className="w-32 h-32">
        <path d={arcPath(225, 270, 40)} stroke="#DDE2E7" strokeWidth={10} fill="none" strokeLinecap="round" />
        <path d={arcPath(225, sweep, 40)} stroke={signal.color ?? "#198ACB"} strokeWidth={10} fill="none" strokeLinecap="round" />
      </svg>
      <span className="text-2xl font-bold text-ink -mt-16">{value}{signal.unit}</span>
      <span className="text-xs text-ink-secondary mt-16">{signal.label ?? signal.signal_key}</span>
    </div>
  );
}
```

- [ ] **Step 4: Write `src/components/charts/KpiTile.tsx`**

```tsx
import type { ChartSignal } from "../../types/dashboard";

export function KpiTile({ signal, value }: { signal: ChartSignal; value: number }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <span className="text-4xl font-extrabold text-ink">{value}</span>
      <span className="text-xs text-ink-secondary">{signal.unit} · {signal.label ?? signal.signal_key}</span>
    </div>
  );
}
```

- [ ] **Step 5: Write `src/components/charts/StatusIndicator.tsx`**

```tsx
export function StatusIndicator({ states }: { states: { label: string; value: string; color: "success" | "warning" | "danger" }[] }) {
  return (
    <div className="h-full flex flex-col justify-center gap-2">
      {states.map((s) => (
        <div key={s.label} className="flex items-center justify-between bg-surface-subtle rounded px-3 py-2">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full bg-${s.color}`} />
            <span className="text-xs text-ink">{s.label}</span>
          </div>
          <span className={`text-xs font-bold text-${s.color}`}>{s.value}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Write `src/components/charts/ValuesTable.tsx`**

```tsx
import type { ChartSignal } from "../../types/dashboard";

export function ValuesTable({
  signals,
  values,
}: {
  signals: ChartSignal[];
  values: Record<string, { value: number; updatedAt: string }>;
}) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-ink-muted uppercase border-b border-border">
          <th className="py-1">Señal</th>
          <th>Valor</th>
          <th>Actualizado</th>
        </tr>
      </thead>
      <tbody>
        {signals.map((s) => {
          const entry = values[s.signal_key];
          return (
            <tr key={s.signal_key} className="border-b border-border-subtle">
              <td className="py-2 font-semibold text-ink">{s.label ?? s.signal_key}</td>
              <td className="text-ink">{entry ? `${entry.value} ${s.unit ?? ""}` : "—"}</td>
              <td className="text-ink-muted">{entry ? entry.updatedAt : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/frontend && npx vitest run src/components/charts/__tests__/GaugeChart.test.tsx`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/components/charts
git commit -m "feat(uns-dashboard): gauge, KPI, status, and values table chart components"
```

---

## Task 17: Refresh interval helper + WS/history hooks

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/lib/refreshInterval.ts`
- Create: `UNS_DASHBOARD/frontend/src/hooks/useHistoricalQuery.ts`
- Create: `UNS_DASHBOARD/frontend/src/hooks/useDashboardSocket.ts`
- Test: `UNS_DASHBOARD/frontend/src/lib/__tests__/refreshInterval.test.ts`

**Interfaces:**
- Produces: `pollIntervalMsFor(rule: RelativeRule): number`; `useHistoricalQuery(chartId: string, rangeType: HistoricalRangeType | null | undefined, relativeRule: RelativeRule | null | undefined): HistoryPoint[]`; `useDashboardSocket(dashboardId: string, topics: string[]): Record<string, {time: string, payload: Record<string, number>}>`.

- [ ] **Step 1: Write the failing test**

```typescript
// src/lib/__tests__/refreshInterval.test.ts
import { describe, expect, it } from "vitest";
import { pollIntervalMsFor } from "../refreshInterval";

describe("pollIntervalMsFor", () => {
  it("polls a 1h window every 30s", () => {
    expect(pollIntervalMsFor("1h")).toBe(30_000);
  });

  it("polls a 30d window every 10 minutes", () => {
    expect(pollIntervalMsFor("30d")).toBe(600_000);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd UNS_DASHBOARD/frontend && npx vitest run src/lib/__tests__/refreshInterval.test.ts`
Expected: FAIL — cannot find module `../refreshInterval`

- [ ] **Step 3: Write `src/lib/refreshInterval.ts`**

```typescript
import type { RelativeRule } from "../types/dashboard";

const INTERVALS_MS: Record<RelativeRule, number> = {
  "1h": 30_000,
  "24h": 120_000,
  "7d": 300_000,
  "30d": 600_000,
};

export function pollIntervalMsFor(rule: RelativeRule): number {
  return INTERVALS_MS[rule];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd UNS_DASHBOARD/frontend && npx vitest run src/lib/__tests__/refreshInterval.test.ts`
Expected: PASS

- [ ] **Step 5: Write `src/hooks/useHistoricalQuery.ts`**

```typescript
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { pollIntervalMsFor } from "../lib/refreshInterval";
import type { HistoricalRangeType, HistoryPoint, RelativeRule } from "../types/dashboard";

export function useHistoricalQuery(
  chartId: string,
  rangeType: HistoricalRangeType | null | undefined,
  relativeRule: RelativeRule | null | undefined
): HistoryPoint[] {
  const [points, setPoints] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = () => {
      api.history.get(chartId).then((res) => {
        if (!cancelled) setPoints(res.points);
      });
    };
    fetchOnce();

    if (rangeType === "relative" && relativeRule) {
      const interval = setInterval(fetchOnce, pollIntervalMsFor(relativeRule));
      return () => {
        cancelled = true;
        clearInterval(interval);
      };
    }
    return () => {
      cancelled = true;
    };
  }, [chartId, rangeType, relativeRule]);

  return points;
}
```

- [ ] **Step 6: Write `src/hooks/useDashboardSocket.ts`**

```typescript
import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api/client";

export interface LiveFrame {
  time: string;
  payload: Record<string, number>;
}

export function useDashboardSocket(dashboardId: string, topics: string[]): Record<string, LiveFrame> {
  const [frames, setFrames] = useState<Record<string, LiveFrame>>({});
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (topics.length === 0) return;

    const connect = () => {
      const socket = new WebSocket(wsUrl(dashboardId));
      socketRef.current = socket;
      socket.onopen = () => socket.send(JSON.stringify({ subscribe: topics }));
      socket.onmessage = (event) => {
        const frame = JSON.parse(event.data);
        setFrames((prev) => ({ ...prev, [frame.topic]: { time: frame.time, payload: frame.payload } }));
      };
      socket.onclose = () => {
        setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      socketRef.current?.close();
    };
  }, [dashboardId, topics.join(",")]);

  return frames;
}
```

- [ ] **Step 7: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/lib/refreshInterval.ts UNS_DASHBOARD/frontend/src/hooks UNS_DASHBOARD/frontend/src/lib/__tests__/refreshInterval.test.ts
git commit -m "feat(uns-dashboard): historical polling cadence and live WebSocket hook"
```

---

## Task 18: Grid workspace (react-grid-layout wrapper)

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/components/editor/GridWorkspace.tsx`

**Interfaces:**
- Consumes: `Chart` type (Task 13).
- Produces: `<GridWorkspace charts: Chart[], editable: boolean, onLayoutChange?: (layouts) => void, renderChart: (chart: Chart) => ReactNode>`.

- [ ] **Step 1: Write `src/components/editor/GridWorkspace.tsx`**

```tsx
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { Responsive, WidthProvider } from "react-grid-layout";
import type { ReactNode } from "react";
import type { Chart } from "../../types/dashboard";

const ResponsiveGridLayout = WidthProvider(Responsive);

export function GridWorkspace({
  charts,
  editable,
  onLayoutChange,
  renderChart,
}: {
  charts: Chart[];
  editable: boolean;
  onLayoutChange?: (layout: { i: string; x: number; y: number; w: number; h: number }[]) => void;
  renderChart: (chart: Chart) => ReactNode;
}) {
  const layout = charts.map((c) => ({ i: c.id, x: c.layout_x, y: c.layout_y, w: c.layout_w, h: c.layout_h }));

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={{ lg: layout }}
      breakpoints={{ lg: 0 }}
      cols={{ lg: 12 }}
      rowHeight={60}
      isDraggable={editable}
      isResizable={editable}
      onLayoutChange={(current) => onLayoutChange?.(current.map((l) => ({ i: l.i, x: l.x, y: l.y, w: l.w, h: l.h })))}
    >
      {charts.map((chart) => (
        <div key={chart.id}>{renderChart(chart)}</div>
      ))}
    </ResponsiveGridLayout>
  );
}
```

- [ ] **Step 2: Manual verification**

Run: `cd UNS_DASHBOARD/frontend && npm run dev` and render `<GridWorkspace>` from a scratch route with 2-3 sample charts (or defer to Task 20's EditorPage integration, where this is exercised end-to-end).
Expected: cards drag and resize when `editable`, are static when not.

- [ ] **Step 3: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/components/editor/GridWorkspace.tsx
git commit -m "feat(uns-dashboard): react-grid-layout workspace wrapper"
```

---

## Task 19: Editor sidebar forms

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/components/editor/DashboardMetaForm.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/editor/SignalPicker.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/editor/ChartForm.tsx`
- Create: `UNS_DASHBOARD/frontend/src/components/editor/PendingChartsList.tsx`

**Interfaces:**
- Consumes: `api.signals.catalog/descriptive` (Task 13).
- Produces: `<DashboardMetaForm name, description, onChange>`; `<SignalPicker selected: ChartSignal[], onChange>`; `<ChartForm onSubmit: (chart: Omit<Chart,"id"|"dashboard_id">) => void>`; `<PendingChartsList charts: Chart[], onRemove>`.

- [ ] **Step 1: Write `src/components/editor/DashboardMetaForm.tsx`**

```tsx
export function DashboardMetaForm({
  name,
  description,
  onChangeName,
  onChangeDescription,
}: {
  name: string;
  description: string;
  onChangeName: (v: string) => void;
  onChangeDescription: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <label className="text-xs font-bold text-ink-muted uppercase">Dashboard</label>
      <input
        className="border border-border rounded-lg px-3 py-2 text-sm"
        value={name}
        onChange={(e) => onChangeName(e.target.value)}
        placeholder="Nombre"
      />
      <textarea
        className="border border-border rounded-lg px-3 py-2 text-sm"
        value={description}
        onChange={(e) => onChangeDescription(e.target.value)}
        placeholder="Descripción"
      />
    </div>
  );
}
```

- [ ] **Step 2: Write `src/components/editor/SignalPicker.tsx`**

```tsx
import { useState } from "react";
import { api } from "../../api/client";
import type { ChartSignal } from "../../types/dashboard";

export function SignalPicker({
  topicPrefix,
  selected,
  onChange,
}: {
  topicPrefix: string;
  selected: ChartSignal[];
  onChange: (signals: ChartSignal[]) => void;
}) {
  const [options, setOptions] = useState<{ topic: string; keys: string[] }[]>([]);

  const search = async () => {
    const catalog = await api.signals.catalog(topicPrefix);
    setOptions(catalog);
  };

  const addSignal = async (topic: string, signalKey: string) => {
    const descriptive = await api.signals.descriptive(topic.replace(/\/_informative$/, ""), signalKey);
    const signal: ChartSignal = {
      topic,
      signal_key: signalKey,
      label: signalKey,
      unit: descriptive.unit ?? null,
      min: descriptive.min ?? null,
      max: descriptive.max ?? null,
      source: descriptive.unit ? "auto" : "manual",
    };
    onChange([...selected, signal]);
  };

  const removeSignal = (signalKey: string) => {
    onChange(selected.filter((s) => s.signal_key !== signalKey));
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between items-center">
        <label className="text-xs font-bold text-ink-secondary">Señales (_informative)</label>
        <button onClick={search} className="text-xs font-semibold text-accent">buscar</button>
      </div>
      <div className="flex flex-wrap gap-2">
        {selected.map((s) => (
          <span key={s.signal_key} className="bg-surface-subtle rounded-full px-3 py-1 text-xs flex items-center gap-1.5">
            {s.label}
            <button onClick={() => removeSignal(s.signal_key)}>✕</button>
          </span>
        ))}
      </div>
      {options.map((topicOpt) => (
        <div key={topicOpt.topic} className="text-xs">
          <div className="text-ink-muted">{topicOpt.topic}</div>
          <div className="flex flex-wrap gap-1">
            {topicOpt.keys.map((key) => (
              <button
                key={key}
                onClick={() => addSignal(topicOpt.topic, key)}
                className="border border-border rounded px-2 py-0.5"
              >
                + {key}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Write `src/components/editor/ChartForm.tsx`**

```tsx
import { useState } from "react";
import { SignalPicker } from "./SignalPicker";
import type { Chart, ChartSignal, ChartType, DataMode, HistoricalRangeType, RelativeRule } from "../../types/dashboard";

const CHART_TYPES: ChartType[] = ["timeseries", "gauge", "kpi", "bar", "table", "status"];
const RELATIVE_RULES: RelativeRule[] = ["1h", "24h", "7d", "30d"];

export function ChartForm({
  topicPrefix,
  onSubmit,
}: {
  topicPrefix: string;
  onSubmit: (chart: Omit<Chart, "id" | "dashboard_id">) => void;
}) {
  const [name, setName] = useState("");
  const [chartType, setChartType] = useState<ChartType>("timeseries");
  const [signals, setSignals] = useState<ChartSignal[]>([]);
  const [dataMode, setDataMode] = useState<DataMode>("live");
  const [rangeType, setRangeType] = useState<HistoricalRangeType>("relative");
  const [relativeRule, setRelativeRule] = useState<RelativeRule>("24h");
  const [color, setColor] = useState("#198ACB");

  const submit = () => {
    onSubmit({
      name,
      chart_type: chartType,
      data_mode: dataMode,
      historical_range_type: dataMode === "historical" ? rangeType : null,
      historical_relative_rule: dataMode === "historical" && rangeType === "relative" ? relativeRule : null,
      historical_from: null,
      historical_to: null,
      layout_x: 0,
      layout_y: 0,
      layout_w: 4,
      layout_h: 4,
      color,
      config: null,
      signals,
    });
    setName("");
    setSignals([]);
  };

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <label className="text-xs font-bold text-ink-muted uppercase">Nueva gráfica</label>
      <input className="border border-border rounded-lg px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre de la gráfica" />

      <select className="border border-border rounded-lg px-3 py-2 text-sm" value={chartType} onChange={(e) => setChartType(e.target.value as ChartType)}>
        {CHART_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>

      <SignalPicker topicPrefix={topicPrefix} selected={signals} onChange={setSignals} />

      <div className="flex gap-2">
        <button className={`flex-1 rounded-lg py-2 text-xs font-semibold ${dataMode === "live" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setDataMode("live")}>Tiempo real</button>
        <button className={`flex-1 rounded-lg py-2 text-xs font-semibold ${dataMode === "historical" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setDataMode("historical")}>Histórico</button>
      </div>

      {dataMode === "historical" && (
        <div className="flex flex-col gap-2 bg-surface-subtle rounded-lg p-3">
          <div className="flex gap-2">
            <button className={`flex-1 rounded py-1 text-xs ${rangeType === "fixed" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setRangeType("fixed")}>Rango fijo</button>
            <button className={`flex-1 rounded py-1 text-xs ${rangeType === "relative" ? "bg-accent text-white" : "border border-border"}`} onClick={() => setRangeType("relative")}>Regla relativa</button>
          </div>
          {rangeType === "relative" && (
            <div className="flex gap-1">
              {RELATIVE_RULES.map((r) => (
                <button key={r} className={`flex-1 rounded py-1 text-xs ${relativeRule === r ? "bg-accent text-white" : "border border-border"}`} onClick={() => setRelativeRule(r)}>{r}</button>
              ))}
            </div>
          )}
        </div>
      )}

      <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-full" />

      <button onClick={submit} disabled={!name || signals.length === 0} className="bg-ink text-white rounded-lg py-2 text-sm font-bold disabled:opacity-40">
        + Añadir al panel
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Write `src/components/editor/PendingChartsList.tsx`**

```tsx
import type { Chart } from "../../types/dashboard";

export function PendingChartsList({ charts, onRemove }: { charts: Chart[]; onRemove: (id: string) => void }) {
  if (charts.length === 0) {
    return <p className="text-xs text-ink-muted">No hay gráficas sin colocar.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {charts.map((c) => (
        <div key={c.id} className="flex items-center justify-between bg-surface-subtle rounded-lg px-3 py-2">
          <div>
            <div className="text-xs font-semibold text-ink">{c.name}</div>
            <div className="text-xs text-ink-muted">{c.chart_type} · {c.data_mode}</div>
          </div>
          <button onClick={() => onRemove(c.id)} className="text-ink-muted text-xs">✕</button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/components/editor
git commit -m "feat(uns-dashboard): editor sidebar forms — dashboard meta, signal picker, chart form"
```

---

## Task 20: Editor page wiring

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/pages/EditorPage.tsx` (replaces stub)

**Interfaces:**
- Consumes: `GridWorkspace` (Task 18), sidebar forms (Task 19), all 6 chart components (Tasks 15-16), `useDashboardSocket`/`useHistoricalQuery` (Task 17), `api.dashboards.*`/`api.charts.*` (Task 13).
- Produces: `<EditorPage>` at `/dashboards/:id/edit`.

- [ ] **Step 1: Write a chart preview renderer shared with Task 22's viewer (extracted here so both pages stay thin)**

```tsx
// src/components/ChartRenderer.tsx
import { ChartCardShell } from "./ChartCardShell";
import { TimeSeriesChart } from "./charts/TimeSeriesChart";
import { BarChart } from "./charts/BarChart";
import { GaugeChart } from "./charts/GaugeChart";
import { KpiTile } from "./charts/KpiTile";
import { StatusIndicator } from "./charts/StatusIndicator";
import { ValuesTable } from "./charts/ValuesTable";
import { useDashboardSocket } from "../hooks/useDashboardSocket";
import { useHistoricalQuery } from "../hooks/useHistoricalQuery";
import type { Chart } from "../types/dashboard";

export function ChartRenderer({ dashboardId, chart, editable, onRemove }: { dashboardId: string; chart: Chart; editable: boolean; onRemove?: () => void }) {
  const topics = chart.data_mode === "live" ? [...new Set(chart.signals.map((s) => s.topic))] : [];
  const liveFrames = useDashboardSocket(dashboardId, topics);
  const historyPoints = useHistoricalQuery(
    chart.id,
    chart.data_mode === "historical" ? chart.historical_range_type : null,
    chart.data_mode === "historical" ? chart.historical_relative_rule : null
  );

  const liveValue = (signalKey: string, topic: string): number =>
    liveFrames[topic]?.payload[signalKey] ?? 0;

  const modeLabel = chart.data_mode === "live"
    ? "Live · tiempo real"
    : chart.historical_range_type === "relative"
      ? `Histórico · ${chart.historical_relative_rule}`
      : "Histórico · rango fijo";

  const body = () => {
    switch (chart.chart_type) {
      case "timeseries":
        return <TimeSeriesChart signals={chart.signals} points={historyPoints} />;
      case "bar": {
        const values = Object.fromEntries(chart.signals.map((s) => [s.signal_key, liveValue(s.signal_key, s.topic)]));
        return <BarChart signals={chart.signals} values={values} />;
      }
      case "gauge":
        return <GaugeChart signal={chart.signals[0]} value={liveValue(chart.signals[0]?.signal_key, chart.signals[0]?.topic)} />;
      case "kpi":
        return <KpiTile signal={chart.signals[0]} value={liveValue(chart.signals[0]?.signal_key, chart.signals[0]?.topic)} />;
      case "status":
        return (
          <StatusIndicator
            states={chart.signals.map((s) => ({ label: s.label ?? s.signal_key, value: String(liveValue(s.signal_key, s.topic)), color: "success" }))}
          />
        );
      case "table": {
        const values = Object.fromEntries(
          chart.signals.map((s) => [s.signal_key, { value: liveValue(s.signal_key, s.topic), updatedAt: liveFrames[s.topic]?.time ?? "—" }])
        );
        return <ValuesTable signals={chart.signals} values={values} />;
      }
    }
  };

  return (
    <ChartCardShell title={chart.name} modeLabel={modeLabel} editable={editable} onRemove={onRemove}>
      {body()}
    </ChartCardShell>
  );
}
```

- [ ] **Step 2: Write `src/pages/EditorPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { GridWorkspace } from "../components/editor/GridWorkspace";
import { DashboardMetaForm } from "../components/editor/DashboardMetaForm";
import { ChartForm } from "../components/editor/ChartForm";
import { ChartRenderer } from "../components/ChartRenderer";
import type { Chart, DashboardDetail } from "../types/dashboard";

export function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);

  const load = () => {
    if (id) api.dashboards.get(id).then(setDashboard);
  };

  useEffect(load, [id]);

  if (!dashboard) return <div className="p-8">Cargando…</div>;

  const saveName = async (name: string) => {
    setDashboard({ ...dashboard, name });
    await api.dashboards.update(dashboard.id, { name });
  };

  const saveDescription = async (description: string) => {
    setDashboard({ ...dashboard, description });
    await api.dashboards.update(dashboard.id, { description });
  };

  const addChart = async (chart: Omit<Chart, "id" | "dashboard_id">) => {
    await api.charts.create(dashboard.id, chart);
    load();
  };

  const removeChart = async (chartId: string) => {
    await api.charts.delete(chartId);
    load();
  };

  const onLayoutChange = async (layout: { i: string; x: number; y: number; w: number; h: number }[]) => {
    for (const l of layout) {
      await api.charts.update(l.i, { layout_x: l.x, layout_y: l.y, layout_w: l.w, layout_h: l.h });
    }
  };

  const publish = async () => {
    await api.dashboards.publish(dashboard.id);
    navigate(`/dashboards/${dashboard.id}`);
  };

  return (
    <div className="flex h-screen">
      <div className="w-96 border-r border-border p-6 overflow-y-auto flex flex-col gap-6">
        <DashboardMetaForm
          name={dashboard.name}
          description={dashboard.description ?? ""}
          onChangeName={saveName}
          onChangeDescription={saveDescription}
        />
        <ChartForm topicPrefix="" onSubmit={addChart} />
        <button onClick={publish} className="bg-accent text-white rounded-lg py-3 font-bold">
          Publicar dashboard
        </button>
      </div>
      <div className="flex-1 p-6 overflow-y-auto bg-surface-subtle">
        <GridWorkspace
          charts={dashboard.charts}
          editable
          onLayoutChange={onLayoutChange}
          renderChart={(chart) => (
            <ChartRenderer dashboardId={dashboard.id} chart={chart} editable onRemove={() => removeChart(chart.id)} />
          )}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Manual verification**

Run: `cd UNS_DASHBOARD/frontend && npm run dev`, open a dashboard's edit page, add a live gauge chart and a historical timeseries chart, drag/resize both, publish.
Expected: charts persist across reload (backed by Task 4's CRUD), publish flips status and redirects to the viewer route.

- [ ] **Step 4: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/pages/EditorPage.tsx UNS_DASHBOARD/frontend/src/components/ChartRenderer.tsx
git commit -m "feat(uns-dashboard): editor page — sidebar forms wired to grid workspace and publish flow"
```

---

## Task 21: Viewer page

**Files:**
- Create: `UNS_DASHBOARD/frontend/src/pages/ViewerPage.tsx` (replaces stub)

**Interfaces:**
- Consumes: `ChartRenderer` (Task 20), `GridWorkspace` (Task 18), `api.dashboards.get` (Task 13).
- Produces: `<ViewerPage>` at `/dashboards/:id`, read-only.

- [ ] **Step 1: Write `src/pages/ViewerPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { GridWorkspace } from "../components/editor/GridWorkspace";
import { ChartRenderer } from "../components/ChartRenderer";
import type { DashboardDetail } from "../types/dashboard";

export function ViewerPage() {
  const { id } = useParams<{ id: string }>();
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);

  useEffect(() => {
    if (id) api.dashboards.get(id).then(setDashboard);
  }, [id]);

  if (!dashboard) return <div className="p-8">Cargando…</div>;

  return (
    <div className="min-h-screen bg-surface-subtle">
      <div className="flex items-center justify-between bg-surface border-b border-border px-8 py-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-ink">{dashboard.name}</h1>
            <span className="bg-surface-subtle text-ink-muted text-xs font-semibold rounded-full px-2 py-0.5">Solo visualización</span>
          </div>
          <p className="text-xs text-ink-secondary">{dashboard.description}</p>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/" className="border border-border rounded-lg px-4 py-2 text-sm font-semibold">Dashboards</Link>
          <Link to={`/dashboards/${dashboard.id}/edit`} className="bg-accent text-white rounded-lg px-4 py-2 text-sm font-bold">Editar</Link>
        </div>
      </div>
      <div className="p-6">
        <GridWorkspace
          charts={dashboard.charts}
          editable={false}
          renderChart={(chart) => <ChartRenderer dashboardId={dashboard.id} chart={chart} editable={false} />}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Manual verification**

Run: publish a dashboard from the Editor (Task 20), navigate to `/dashboards/:id`, confirm charts render without drag/resize/remove affordances and live charts update as MQTT readings arrive.
Expected: matches the "03 Viewer" mockup — fixed layout, live badge implicit in each chart's mode chip.

- [ ] **Step 3: Commit**

```bash
git add UNS_DASHBOARD/frontend/src/pages/ViewerPage.tsx
git commit -m "feat(uns-dashboard): read-only viewer page for published dashboards"
```

---

## Task 22: End-to-end smoke verification

**Files:**
- Create: `UNS_DASHBOARD/README.md`

**Interfaces:**
- None — this task documents and manually exercises the full pipeline built by Tasks 1-21.

- [ ] **Step 1: Write `UNS_DASHBOARD/README.md`**

```markdown
# UNS Dashboard

Real-time SCADA dashboard authoring and viewing. See
`docs/superpowers/specs/2026-09-03-uns-dashboard-design.md` for the full design.

## Running standalone

Requires `UNS_MANAGER` (for EMQX) and `UNS_HISTORIAN` (for history/signal catalog) already running:

```bash
cd UNS_MANAGER && docker compose up -d
cd ../UNS_HISTORIAN && docker compose up -d
cd ../UNS_DASHBOARD && cp .env.example .env && ./scripts/up.sh
```

- Backend: http://localhost:8001 (docs at `/docs`)
- Frontend: http://localhost:3002

## End-to-end smoke test

1. `docker compose up -d` from the repo root (brings up all three stacks together).
2. Open the frontend, create a dashboard, add a `live` gauge chart bound to an
   existing `_informative` signal (use the signal picker's "buscar" button —
   it lists topics already captured by `UNS_HISTORIAN`).
3. Publish the dashboard and open its viewer URL.
4. Publish a synthetic reading: `mosquitto_pub -h localhost -p 1883 -t '<topic>' -m '{"<signal_key>": 42}'`.
5. Confirm the gauge updates within ~1s — this exercises the full
   `EMQX → bridge → Redis Stream → backend WebSocket → browser` path.
6. Add a `historical` `relative: 24h` timeseries chart on the same signal,
   confirm it renders points from `UNS_HISTORIAN` (seeded by step 4 and any
   prior traffic on that topic).
```

- [ ] **Step 2: Run the full smoke test**

Follow the README's "End-to-end smoke test" section exactly.
Expected: every step succeeds as described; the live gauge updates within ~1s of the `mosquitto_pub` call, and the historical chart shows at least the one seeded point.

- [ ] **Step 3: Run the complete backend test suite once more, fully wired**

Run: `cd UNS_DASHBOARD/backend && DATABASE_URL=postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard HISTORIAN_DATABASE_URL=postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian pytest tests/ -v`
Expected: all tests PASS, none skipped.

- [ ] **Step 4: Run the complete frontend test suite**

Run: `cd UNS_DASHBOARD/frontend && npm run test`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add UNS_DASHBOARD/README.md
git commit -m "docs(uns-dashboard): README with standalone run instructions and e2e smoke test"
```

---

## Self-Review Notes

- **Spec coverage:** architecture (Task 12), data model (Task 2), real-time pipeline (Tasks 5-6, 11), historical pipeline (Tasks 7-9), signal catalog/descriptive prefill (Task 10), frontend's three screens (Tasks 14, 20, 21), the 6 chart types (Tasks 15-16), deployment (Task 12), testing (embedded throughout + Task 22). All spec sections have a corresponding task.
- **Placeholder scan:** no TBD/TODO; every step has runnable code or an explicit manual-verification procedure with expected output.
- **Type consistency:** `Chart`/`ChartSignal`/`Dashboard` field names match verbatim between backend Pydantic schemas (Task 2), the history/signals routers (Tasks 9-10), and the frontend `types/dashboard.ts` (Task 13) — `layout_x/y/w/h`, `data_mode`, `historical_range_type`, `historical_relative_rule`, `signal_key` are spelled identically everywhere they cross the API boundary.
- **Scope check:** one cohesive module (single spec, single milestone); task count (22) reflects genuine layering (models → routers → pipeline → frontend), not artificial splitting.
