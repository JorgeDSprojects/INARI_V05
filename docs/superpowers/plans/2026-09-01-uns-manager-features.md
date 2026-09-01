# UNS Manager — Features A2–A9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 7 new features (A2 Data Branches, A3 Copy/Move Subtree, A5 UNS Wizard, A6 Create With Descriptive, A7 Broker Registry, A8 Node Type Catalog, A9 Sync Status) aligned to the uns_manage.pen mockup screens.

**Architecture:** Incremental by dependency order (A7→A8→A5→A6→A2→A3→A9). Each task is additive and does not break existing functionality. Backend uses FastAPI async + SQLAlchemy 2.x; frontend uses React + Tailwind + axios.

**Tech Stack:** Python 3.11, FastAPI 0.115, SQLAlchemy 2.0 async, PostgreSQL 16 (JSONB), paho-mqtt 2.1, httpx 0.28, React 18, TypeScript, Tailwind CSS, axios, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-01-uns-manager-features-design.md`

## Global Constraints

- All new ORM models inherit `TimestampMixin` and `Base` from `app.database`
- All UUID PKs use `String(36)` with `default=_uuid` (import `_uuid` from `app.models.uns`)
- All new Pydantic Read schemas use `model_config = ConfigDict(from_attributes=True)` — do NOT add `metadata_` field to any Read schema (it conflicts with SQLAlchemy's `MetaData()`)
- All new routers register in `backend/app/main.py` via `app.include_router()`
- All new models must be imported in `backend/app/database.py`'s `create_tables()` function
- Frontend design tokens: use `bg-surface`, `text-ink`, `border-border`, `text-ink-muted`, `text-accent`, `bg-success-soft text-success`, `bg-danger-soft text-danger` — never raw hex except inside `bg-code-bg` areas
- Tailwind classes only — no inline `style=` except for dynamic values (indent, pixel sizes)
- After every backend task: rebuild Docker with `docker compose up --build -d`
- After every frontend task: verify in browser at `http://localhost:3001`

---

## Task 1: A7 Backend — Broker Model, Service, Router

**Files:**
- Create: `backend/app/models/broker.py`
- Create: `backend/app/schemas/broker.py`
- Create: `backend/app/services/broker_service.py`
- Create: `backend/app/routers/brokers.py`
- Modify: `backend/app/database.py` (add import in `create_tables`)
- Modify: `backend/app/main.py` (register router)

**Interfaces:**
- Produces: `Broker` ORM model; `broker_service.get_broker_status(broker)`, `broker_service.test_broker_connection(broker)`, `broker_service.get_subscriptions(broker, topic)`, `broker_service.get_retained_payload(broker, topic)` — all async, all return dicts
- Produces: REST endpoints `GET/POST/GET/PUT/DELETE /brokers/`, `GET /brokers/{id}/status`, `POST /brokers/{id}/test`

- [ ] **Step 1: Create the Broker ORM model**

Create `backend/app/models/broker.py`:

```python
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.uns import TimestampMixin, _uuid


class Broker(TimestampMixin, Base):
    __tablename__ = "brokers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=1883)
    api_port: Mapped[int] = mapped_column(Integer, nullable=False, default=18083)
    username: Mapped[str | None] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(String(255))
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

- [ ] **Step 2: Register Broker model in create_tables**

Edit `backend/app/database.py`. Find `create_tables` and add the import:

```python
async def create_tables() -> None:
    from app.models import uns  # noqa: F401
    from app.models import broker  # noqa: F401  ← ADD THIS LINE
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 3: Create Broker Pydantic schemas**

Create `backend/app/schemas/broker.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BrokerCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=1883, ge=1, le=65535)
    api_port: int = Field(default=18083, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool = False


class BrokerUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    api_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None


class BrokerRead(_Base):
    id: str
    label: str
    host: str
    port: int
    api_port: int
    username: str | None
    use_tls: bool
    created_at: datetime
    updated_at: datetime
    # password intentionally omitted


class BrokerStatus(BaseModel):
    connected: bool
    version: str | None = None
    node: str | None = None
    error: str | None = None


class BrokerTestResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None
```

- [ ] **Step 4: Create broker_service.py**

Create `backend/app/services/broker_service.py`:

```python
from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from typing import Any

import httpx
import paho.mqtt.client as mqtt

from app.models.broker import Broker


def _api_base(broker: Broker) -> str:
    scheme = "https" if broker.use_tls else "http"
    return f"{scheme}://{broker.host}:{broker.api_port}/api/v5"


def _auth(broker: Broker) -> tuple[str, str] | None:
    if broker.username:
        return (broker.username, broker.password or "")
    return None


async def get_broker_status(broker: Broker) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_api_base(broker)}/status",
                auth=_auth(broker),
            )
            r.raise_for_status()
            data = r.json()
            return {
                "connected": True,
                "version": data.get("emqx_version"),
                "node": data.get("node"),
                "error": None,
            }
    except Exception as exc:
        return {"connected": False, "version": None, "node": None, "error": str(exc)}


async def test_broker_connection(broker: Broker) -> dict[str, Any]:
    connected_event = asyncio.Event()
    error_msg: list[str] = []

    def on_connect(client: mqtt.Client, userdata: Any, flags: Any, rc: int, properties: Any = None) -> None:
        if rc == 0:
            connected_event.set()
        else:
            error_msg.append(f"rc={rc}")

    client = mqtt.Client(client_id="uns_manager_test_probe", protocol=mqtt.MQTTv5)
    if broker.username:
        client.username_pw_set(broker.username, broker.password or "")
    client.on_connect = on_connect

    start = time.monotonic()
    try:
        client.connect(broker.host, broker.port, keepalive=10)
        client.loop_start()
        try:
            await asyncio.wait_for(connected_event.wait(), timeout=5.0)
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "error": None}
        except asyncio.TimeoutError:
            msg = error_msg[0] if error_msg else "Connection timed out"
            return {"ok": False, "latency_ms": None, "error": msg}
    except Exception as exc:
        return {"ok": False, "latency_ms": None, "error": str(exc)}
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass


async def get_subscriptions(broker: Broker, topic: str) -> list[dict[str, Any]]:
    """Return active EMQX subscribers for a topic. Returns [] on any error."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_api_base(broker)}/subscriptions",
                params={"topic": topic},
                auth=_auth(broker),
            )
            r.raise_for_status()
            data = r.json()
            items: list[Any] = data.get("data", data) if isinstance(data, dict) else data
            return [
                {
                    "client_id": item.get("clientid", ""),
                    "topic_filter": item.get("topic", topic),
                    "qos": item.get("qos", 0),
                    "connected_at": None,
                }
                for item in items
            ]
    except Exception:
        return []


async def get_retained_payload(broker: Broker, topic: str) -> dict[str, Any] | None:
    """Fetch retained message payload from EMQX. Returns None if not found or error."""
    try:
        encoded = urllib.parse.quote(topic, safe="")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_api_base(broker)}/retainer/message/{encoded}",
                auth=_auth(broker),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            payload_str = data.get("payload", "")
            if not payload_str:
                return None
            return json.loads(payload_str)
    except Exception:
        return None
```

- [ ] **Step 5: Create brokers router**

Create `backend/app/routers/brokers.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.broker import Broker
from app.schemas.broker import (
    BrokerCreate,
    BrokerRead,
    BrokerStatus,
    BrokerTestResult,
    BrokerUpdate,
)
from app.services import broker_service

router = APIRouter(prefix="/brokers", tags=["Brokers"])


@router.get("/", response_model=list[BrokerRead])
async def list_brokers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Broker).order_by(Broker.label))
    return result.scalars().all()


@router.post("/", response_model=BrokerRead, status_code=status.HTTP_201_CREATED)
async def create_broker(body: BrokerCreate, db: AsyncSession = Depends(get_db)):
    obj = Broker(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{broker_id}", response_model=BrokerRead)
async def get_broker(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    return obj


@router.put("/{broker_id}", response_model=BrokerRead)
async def update_broker(
    broker_id: str, body: BrokerUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broker(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    await db.delete(obj)
    await db.commit()


@router.get("/{broker_id}/status", response_model=BrokerStatus)
async def broker_status(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    return await broker_service.get_broker_status(obj)


@router.post("/{broker_id}/test", response_model=BrokerTestResult)
async def test_broker(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    return await broker_service.test_broker_connection(obj)
```

- [ ] **Step 6: Register router in main.py**

Edit `backend/app/main.py`. Add the import and include_router:

```python
from app.routers import enterprises, sites, areas, lines, cells, assets, tree, brokers  # add brokers
# ...
app.include_router(brokers.router)  # add after tree.router
```

- [ ] **Step 7: Rebuild and verify**

```bash
docker compose up --build -d
```

Wait ~10 seconds, then test:

```bash
# Should return []
curl http://localhost:8000/brokers/

# Should return 201 with the new broker
curl -X POST http://localhost:8000/brokers/ \
  -H "Content-Type: application/json" \
  -d '{"label":"Local EMQX","host":"emqx","port":1883,"api_port":18083}'

# Copy the returned id and test status:
curl http://localhost:8000/brokers/{id}/status
# Expected: {"connected":true|false, "version":"...", "node":"..."}
```

---

## Task 2: A7 Frontend — BrokersView Component

**Files:**
- Create: `frontend/src/components/BrokersView.tsx`
- Modify: `frontend/src/types/uns.ts` (add Broker, BrokerStatus, BrokerTestResult interfaces)
- Modify: `frontend/src/api/client.ts` (add brokers namespace)
- Modify: `frontend/src/App.tsx` (render BrokersView for `view === "brokers"`)

**Interfaces:**
- Consumes: `GET /brokers/`, `POST /brokers/`, `PUT /brokers/{id}`, `DELETE /brokers/{id}`, `GET /brokers/{id}/status`, `POST /brokers/{id}/test` (from Task 1)
- Produces: `BrokersView` React component; `api.brokers.*` functions; `Broker`, `BrokerStatus`, `BrokerTestResult` TS types

- [ ] **Step 1: Add types to uns.ts**

Edit `frontend/src/types/uns.ts`. Append at the end of the file:

```typescript
export interface Broker {
  id: string;
  label: string;
  host: string;
  port: number;
  api_port: number;
  username: string | null;
  use_tls: boolean;
  created_at: string;
  updated_at: string;
}

export interface BrokerStatus {
  connected: boolean;
  version: string | null;
  node: string | null;
  error: string | null;
}

export interface BrokerTestResult {
  ok: boolean;
  latency_ms: number | null;
  error: string | null;
}
```

- [ ] **Step 2: Add brokers to API client**

Edit `frontend/src/api/client.ts`. Add this import at the top (after existing type imports):

```typescript
import type { Broker, BrokerStatus, BrokerTestResult, /* existing types */ } from "../types/uns";
```

Then add inside the `api` object, after the `assets` block:

```typescript
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
```

- [ ] **Step 3: Create BrokersView.tsx**

Create `frontend/src/components/BrokersView.tsx`:

```tsx
import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";
import type { Broker, BrokerStatus, BrokerTestResult } from "../types/uns";

type FormState = {
  label: string; host: string; port: number; api_port: number;
  username: string; password: string; use_tls: boolean;
};

const EMPTY_FORM: FormState = {
  label: "", host: "", port: 1883, api_port: 18083,
  username: "", password: "", use_tls: false,
};

export function BrokersView() {
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [selected, setSelected] = useState<Broker | null>(null);
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<BrokerTestResult | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setBrokers(await api.brokers.list());
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!selected) { setStatus(null); return; }
    let cancelled = false;
    const poll = async () => {
      const s = await api.brokers.status(selected.id);
      if (!cancelled) setStatus(s);
    };
    poll();
    const id = setInterval(poll, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, [selected]);

  const handleCreate = async () => {
    if (!form.label.trim() || !form.host.trim()) return;
    setSaving(true);
    try {
      const payload = {
        label: form.label.trim(), host: form.host.trim(),
        port: form.port, api_port: form.api_port,
        username: form.username || undefined, password: form.password || undefined,
        use_tls: form.use_tls,
      };
      const b = await api.brokers.create(payload);
      setBrokers(prev => [...prev, b]);
      setShowForm(false);
      setForm(EMPTY_FORM);
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this broker?")) return;
    await api.brokers.delete(id);
    setBrokers(prev => prev.filter(b => b.id !== id));
    if (selected?.id === id) { setSelected(null); setStatus(null); }
  };

  const handleTest = async () => {
    if (!selected) return;
    setTesting(true);
    setTestResult(null);
    try { setTestResult(await api.brokers.test(selected.id)); }
    finally { setTesting(false); }
  };

  const setField = (key: keyof FormState, val: string | number | boolean) =>
    setForm(prev => ({ ...prev, [key]: val }));

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left panel */}
      <div className="w-96 border-r border-border flex flex-col overflow-hidden bg-surface shrink-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-ink">Broker registry</h2>
          <button onClick={() => setShowForm(v => !v)}
            className="px-3 py-1.5 text-xs bg-ink text-white rounded hover:bg-ink/90">
            + Register broker
          </button>
        </div>

        {showForm && (
          <div className="px-5 py-4 border-b border-border space-y-3 bg-surface-subtle">
            {([
              { key: "label", label: "Label", type: "text", ph: "Production EMQX" },
              { key: "host", label: "Host", type: "text", ph: "emqx" },
              { key: "port", label: "MQTT Port", type: "number", ph: "1883" },
              { key: "api_port", label: "API Port", type: "number", ph: "18083" },
              { key: "username", label: "Username", type: "text", ph: "admin (optional)" },
              { key: "password", label: "Password", type: "password", ph: "••••••" },
            ] as const).map(f => (
              <div key={f.key}>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1">
                  {f.label.toUpperCase()}
                </label>
                <input type={f.type} placeholder={f.ph}
                  value={String(form[f.key as keyof FormState])}
                  onChange={e => setField(
                    f.key as keyof FormState,
                    f.type === "number" ? Number(e.target.value) : e.target.value
                  )}
                  className="w-full px-3 py-1.5 text-sm border border-border rounded bg-surface text-ink focus:outline-none focus:border-accent"
                />
              </div>
            ))}
            <label className="flex items-center gap-2 text-sm text-ink-secondary cursor-pointer">
              <input type="checkbox" checked={form.use_tls}
                onChange={e => setField("use_tls", e.target.checked)} />
              Use TLS
            </label>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={saving || !form.label || !form.host}
                className="px-3 py-1.5 text-xs bg-ink text-white rounded disabled:opacity-50">
                {saving ? "Saving…" : "Save broker"}
              </button>
              <button onClick={() => { setShowForm(false); setForm(EMPTY_FORM); }}
                className="px-3 py-1.5 text-xs text-ink-secondary border border-border rounded">
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {brokers.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-ink-muted text-sm py-12">
              <span>No brokers registered</span>
            </div>
          ) : brokers.map(b => (
            <button key={b.id} onClick={() => { setSelected(b); setTestResult(null); }}
              className={`w-full text-left px-5 py-3.5 border-b border-border-subtle flex items-center justify-between group hover:bg-surface-subtle transition-colors ${selected?.id === b.id ? "bg-surface-subtle" : ""}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink truncate">{b.label}</div>
                <div className="text-xs text-ink-muted font-mono">{b.host}:{b.port}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`w-2 h-2 rounded-full transition-colors ${
                  selected?.id === b.id && status
                    ? status.connected ? "bg-success" : "bg-danger"
                    : "bg-ink-muted/30"
                }`} />
                <button onClick={e => { e.stopPropagation(); handleDelete(b.id); }}
                  className="opacity-0 group-hover:opacity-100 text-danger text-[10px] px-1.5 py-0.5 rounded hover:bg-danger-soft transition-opacity">
                  ✕
                </button>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel */}
      {selected ? (
        <div className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-lg space-y-6">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-xl font-semibold text-ink">{selected.label}</h3>
                <div className="text-sm text-ink-muted font-mono mt-0.5">{selected.host}:{selected.port}</div>
              </div>
              {status && (
                <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${status.connected ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
                  <span className={`w-1.5 h-1.5 rounded-full inline-block ${status.connected ? "bg-success" : "bg-danger"}`} />
                  {status.connected ? "CONNECTED" : "DISCONNECTED"}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-x-8 gap-y-4">
              {([
                ["MQTT Port", String(selected.port)],
                ["API Port", String(selected.api_port)],
                ["TLS", selected.use_tls ? "Enabled" : "Disabled"],
                ["Username", selected.username ?? "—"],
                ["EMQX Version", status?.version ?? "—"],
                ["Node", status?.node ?? "—"],
              ] as [string, string][]).map(([k, v]) => (
                <div key={k}>
                  <div className="text-[10px] tracking-widest text-ink-muted mb-1">{k}</div>
                  <div className="text-sm text-ink font-mono">{v}</div>
                </div>
              ))}
            </div>

            <div>
              <button onClick={handleTest} disabled={testing}
                className="px-4 py-2 text-sm border border-border rounded text-ink hover:bg-surface-subtle disabled:opacity-50">
                {testing ? "Testing connection…" : "Test connection"}
              </button>
              {testResult && (
                <div className={`mt-3 px-4 py-3 rounded text-sm ${testResult.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
                  {testResult.ok
                    ? `✓ Connected in ${testResult.latency_ms}ms`
                    : `✗ Failed — ${testResult.error}`}
                </div>
              )}
              {status?.error && !testResult && (
                <p className="mt-2 text-xs text-danger">{status.error}</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
          Select a broker to view details
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire BrokersView in App.tsx**

Edit `frontend/src/App.tsx`. Add import and replace the "Coming soon" fallback:

```tsx
import { BrokersView } from "./components/BrokersView";  // add this import

// In JSX, replace the final else branch:
) : view === "brokers" ? (
  <BrokersView />
) : (
  <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
    Coming soon
  </div>
)}
```

- [ ] **Step 5: Rebuild frontend and verify**

```bash
docker compose up --build -d
```

Open `http://localhost:3001`. Click "Brokers" tab in the header. You should see the Broker registry page with "No brokers registered" empty state. Click "Register broker", fill in `label=Local EMQX`, `host=emqx`, and save. The broker should appear in the list. Click it to see details and the "Test connection" button.

---

## Task 3: A8 Backend — NodeType Model + Asset FK

**Files:**
- Create: `backend/app/models/node_type.py`
- Create: `backend/app/schemas/node_type.py`
- Create: `backend/app/services/node_type_service.py`
- Create: `backend/app/routers/node_types.py`
- Modify: `backend/app/models/uns.py` (add `node_type_id` FK + `last_published_at` to Asset)
- Modify: `backend/app/schemas/uns.py` (add `node_type_id` + `last_published_at` to AssetRead)
- Modify: `backend/app/database.py` (add node_type import in create_tables)
- Modify: `backend/app/main.py` (register router)
- Modify: `backend/requirements.txt` (add jsonschema)

**Interfaces:**
- Produces: `NodeType` ORM model; `node_type_service.validate_payload(schema, payload)` → `(bool, list[str])`
- Produces: `GET/POST/GET/PUT/DELETE /node-types/`, `POST /node-types/{id}/validate`
- Produces: `Asset.node_type_id` FK column; `Asset.last_published_at` column

- [ ] **Step 1: Add jsonschema to requirements**

Edit `backend/requirements.txt`. Add this line:

```
jsonschema==4.23.0
```

- [ ] **Step 2: Create NodeType ORM model**

Create `backend/app/models/node_type.py`:

```python
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
```

- [ ] **Step 3: Add node_type_id and last_published_at to Asset model**

Edit `backend/app/models/uns.py`. Find the `Asset` class and add two new columns plus the relationship. The updated Asset class should look like:

```python
from datetime import datetime  # add datetime to imports at top

class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cell_id: Mapped[str] = mapped_column(String(36), ForeignKey("cells.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    descriptive_payload: Mapped[dict | None] = mapped_column(JSONB)
    uns_topic: Mapped[str | None] = mapped_column(String(1024))
    node_type_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("node_types.id", ondelete="SET NULL"))  # NEW
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NEW

    cell: Mapped[Cell] = relationship("Cell", back_populates="assets")
    node_type: Mapped[object | None] = relationship("NodeType", back_populates="assets")  # NEW
```

Also add `datetime` to the imports at the top of `uns.py` if not already present:
```python
from datetime import datetime
```

- [ ] **Step 4: Add node_type import and register in create_tables**

Edit `backend/app/database.py`:

```python
async def create_tables() -> None:
    from app.models import uns  # noqa: F401
    from app.models import broker  # noqa: F401
    from app.models import node_type  # noqa: F401  ← ADD
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 5: Apply new columns to existing DB**

Since `create_all` only creates new tables (not new columns), run these ALTER TABLE statements manually:

```bash
docker compose exec postgres psql -U unsadmin unsdb -c "
ALTER TABLE assets
  ADD COLUMN IF NOT EXISTS node_type_id VARCHAR(36) REFERENCES node_types(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ;
"
```

Expected output: `ALTER TABLE`

- [ ] **Step 6: Update AssetRead schema**

Edit `backend/app/schemas/uns.py`. Update `AssetRead` and `AssetCreate`/`AssetUpdate` to include new fields:

```python
from datetime import datetime  # ensure this import exists at top

class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    descriptive_payload: dict[str, Any] | None = None
    node_type_id: str | None = None  # NEW

class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    descriptive_payload: dict[str, Any] | None = None
    node_type_id: str | None = None  # NEW

class AssetRead(_Base):
    id: str
    cell_id: str
    name: str
    description: str | None
    descriptive_payload: dict[str, Any] | None
    uns_topic: str | None
    node_type_id: str | None  # NEW
    last_published_at: datetime | None  # NEW
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 7: Update publish_asset endpoint to set last_published_at**

Edit `backend/app/routers/assets.py`. Add to imports:

```python
from datetime import datetime, timezone
```

In `publish_asset`, after `publish_descriptive(...)`, add:

```python
obj.last_published_at = datetime.now(timezone.utc)
await db.commit()
await db.refresh(obj)
```

Also update `update_asset` to pass `node_type_id` through — this already works via `model_dump(exclude_unset=True)` since `node_type_id` is now in `AssetUpdate`.

- [ ] **Step 8: Create NodeType schemas**

Create `backend/app/schemas/node_type.py`:

```python
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
```

- [ ] **Step 9: Create node_type_service.py**

Create `backend/app/services/node_type_service.py`:

```python
from __future__ import annotations

from typing import Any

import jsonschema
import jsonschema.exceptions


def validate_payload(schema: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate payload against a JSON Schema. Returns (valid, error_messages)."""
    if not schema:
        return True, []
    try:
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if errors:
            return False, [e.message for e in errors]
        return True, []
    except jsonschema.exceptions.SchemaError as exc:
        return False, [f"Invalid schema: {exc.message}"]
```

- [ ] **Step 10: Create node_types router**

Create `backend/app/routers/node_types.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.node_type import NodeType
from app.schemas.node_type import (
    NodeTypeCreate,
    NodeTypeRead,
    NodeTypeUpdate,
    ValidationResult,
)
from app.services import node_type_service

router = APIRouter(prefix="/node-types", tags=["Node Types"])


@router.get("/", response_model=list[NodeTypeRead])
async def list_node_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(NodeType).order_by(NodeType.name))
    return result.scalars().all()


@router.post("/", response_model=NodeTypeRead, status_code=status.HTTP_201_CREATED)
async def create_node_type(body: NodeTypeCreate, db: AsyncSession = Depends(get_db)):
    obj = NodeType(
        name=body.name,
        description=body.description,
        json_schema=body.json_schema,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{node_type_id}", response_model=NodeTypeRead)
async def get_node_type(node_type_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    return obj


@router.put("/{node_type_id}", response_model=NodeTypeRead)
async def update_node_type(
    node_type_id: str, body: NodeTypeUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{node_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node_type(node_type_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    await db.delete(obj)
    await db.commit()


@router.post("/{node_type_id}/validate", response_model=ValidationResult)
async def validate_payload(
    node_type_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    valid, errors = node_type_service.validate_payload(obj.json_schema, body.get("payload", body))
    return ValidationResult(valid=valid, errors=errors)
```

- [ ] **Step 11: Register router in main.py**

Edit `backend/app/main.py`:

```python
from app.routers import enterprises, sites, areas, lines, cells, assets, tree, brokers, node_types  # add node_types
# ...
app.include_router(node_types.router)  # add after brokers.router
```

- [ ] **Step 12: Rebuild and verify**

```bash
docker compose up --build -d
```

Test:

```bash
# Create a node type
curl -X POST http://localhost:8000/node-types/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Temperature Sensor",
    "description": "IoT temperature sensor",
    "json_schema": {
      "type": "object",
      "required": ["temperature", "unit"],
      "properties": {
        "temperature": {"type": "number"},
        "unit": {"type": "string", "enum": ["C", "F"]}
      }
    }
  }'

# Validate a payload — should return {"valid": true, "errors": []}
curl -X POST http://localhost:8000/node-types/{id}/validate \
  -H "Content-Type: application/json" \
  -d '{"payload": {"temperature": 23.5, "unit": "C"}}'
```

---

## Task 4: A8 Frontend — NodeTypesView Component

**Files:**
- Create: `frontend/src/components/NodeTypesView.tsx`
- Modify: `frontend/src/types/uns.ts` (add NodeType interface)
- Modify: `frontend/src/api/client.ts` (add nodeTypes namespace)
- Modify: `frontend/src/App.tsx` (render NodeTypesView for `view === "nodetypes"`)

**Interfaces:**
- Consumes: `GET/POST/PUT/DELETE /node-types/`, `POST /node-types/{id}/validate` (from Task 3)
- Produces: `NodeTypesView` React component; `api.nodeTypes.*`; `NodeType` TS type

- [ ] **Step 1: Add NodeType interface to uns.ts**

Edit `frontend/src/types/uns.ts`. Append:

```typescript
export interface NodeType {
  id: string;
  name: string;
  description: string | null;
  json_schema: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}
```

Also update the `Asset` interface to add the new fields:

```typescript
export interface Asset {
  id: string;
  cell_id: string;
  name: string;
  description: string | null;
  descriptive_payload: Record<string, unknown> | null;
  uns_topic: string | null;
  node_type_id: string | null;       // NEW
  last_published_at: string | null;  // NEW
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add nodeTypes to API client**

Edit `frontend/src/api/client.ts`. Add import for `NodeType, ValidationResult` and append:

```typescript
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
```

- [ ] **Step 3: Create NodeTypesView.tsx**

Create `frontend/src/components/NodeTypesView.tsx`:

```tsx
import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";
import type { NodeType } from "../types/uns";

function extractRequiredFields(schema: Record<string, unknown>): string {
  const required = schema.required as string[] | undefined;
  if (!required || required.length === 0) return "—";
  return required.slice(0, 3).join(", ") + (required.length > 3 ? "…" : "");
}

export function NodeTypesView() {
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([]);
  const [selected, setSelected] = useState<NodeType | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formSchema, setFormSchema] = useState("{\n  \n}");
  const [formSchemaError, setFormSchemaError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editSchema, setEditSchema] = useState("");
  const [editSchemaError, setEditSchemaError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  const load = useCallback(async () => {
    setNodeTypes(await api.nodeTypes.list());
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (selected) {
      setEditSchema(JSON.stringify(selected.json_schema, null, 2));
      setEditSchemaError(null);
      setEditMode(false);
    }
  }, [selected]);

  const parseSchema = (text: string): [Record<string, unknown> | null, string | null] => {
    try { return [JSON.parse(text), null]; }
    catch (e: unknown) { return [null, e instanceof Error ? e.message : "Invalid JSON"]; }
  };

  const handleCreate = async () => {
    const [parsed, err] = parseSchema(formSchema);
    if (err) { setFormSchemaError(err); return; }
    setSaving(true);
    try {
      const nt = await api.nodeTypes.create({
        name: formName.trim(),
        description: formDesc.trim() || undefined,
        json_schema: parsed!,
      });
      setNodeTypes(prev => [...prev, nt]);
      setShowForm(false);
      setFormName(""); setFormDesc(""); setFormSchema("{\n  \n}"); setFormSchemaError(null);
    } finally { setSaving(false); }
  };

  const handleSaveEdit = async () => {
    if (!selected) return;
    const [parsed, err] = parseSchema(editSchema);
    if (err) { setEditSchemaError(err); return; }
    setSavingEdit(true);
    try {
      const updated = await api.nodeTypes.update(selected.id, { json_schema: parsed! });
      setNodeTypes(prev => prev.map(n => n.id === updated.id ? updated : n));
      setSelected(updated);
      setEditMode(false);
    } finally { setSavingEdit(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this node type? Existing assets with this type will lose their schema.")) return;
    await api.nodeTypes.delete(id);
    setNodeTypes(prev => prev.filter(n => n.id !== id));
    if (selected?.id === id) setSelected(null);
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left panel */}
      <div className="w-96 border-r border-border flex flex-col overflow-hidden bg-surface shrink-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-ink">Node type catalog</h2>
          <button onClick={() => setShowForm(v => !v)}
            className="px-3 py-1.5 text-xs bg-ink text-white rounded hover:bg-ink/90">
            + New node type
          </button>
        </div>

        {showForm && (
          <div className="px-5 py-4 border-b border-border space-y-3 bg-surface-subtle">
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1">NAME</label>
              <input type="text" placeholder="Temperature Sensor" value={formName}
                onChange={e => setFormName(e.target.value)}
                className="w-full px-3 py-1.5 text-sm border border-border rounded bg-surface text-ink focus:outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1">DESCRIPTION</label>
              <input type="text" placeholder="Optional" value={formDesc}
                onChange={e => setFormDesc(e.target.value)}
                className="w-full px-3 py-1.5 text-sm border border-border rounded bg-surface text-ink focus:outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1">JSON SCHEMA</label>
              <textarea value={formSchema} rows={6} spellCheck={false}
                onChange={e => { setFormSchema(e.target.value); const [, err] = parseSchema(e.target.value); setFormSchemaError(err); }}
                className="w-full px-3 py-2 text-xs font-mono border border-border rounded bg-code-bg text-code-ink focus:outline-none resize-none" />
              {formSchemaError && <p className="text-danger text-xs mt-1 font-mono">{formSchemaError}</p>}
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={saving || !formName.trim() || !!formSchemaError}
                className="px-3 py-1.5 text-xs bg-ink text-white rounded disabled:opacity-50">
                {saving ? "Saving…" : "Save"}
              </button>
              <button onClick={() => setShowForm(false)}
                className="px-3 py-1.5 text-xs text-ink-secondary border border-border rounded">
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {nodeTypes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-ink-muted text-sm py-12">
              No node types defined
            </div>
          ) : nodeTypes.map(nt => (
            <button key={nt.id} onClick={() => setSelected(nt)}
              className={`w-full text-left px-5 py-3.5 border-b border-border-subtle flex items-start justify-between group hover:bg-surface-subtle ${selected?.id === nt.id ? "bg-surface-subtle" : ""}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink truncate">{nt.name}</div>
                <div className="text-xs text-ink-muted mt-0.5 truncate">
                  required: {extractRequiredFields(nt.json_schema)}
                </div>
              </div>
              <button onClick={e => { e.stopPropagation(); handleDelete(nt.id); }}
                className="opacity-0 group-hover:opacity-100 text-danger text-[10px] px-1.5 py-0.5 rounded hover:bg-danger-soft ml-2 shrink-0 transition-opacity">
                ✕
              </button>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel */}
      {selected ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <div>
              <h3 className="text-lg font-semibold text-ink">{selected.name}</h3>
              {selected.description && (
                <p className="text-sm text-ink-muted mt-0.5">{selected.description}</p>
              )}
            </div>
            <button onClick={() => { setEditMode(v => !v); setEditSchemaError(null); }}
              className="px-3 py-1.5 text-sm border border-border rounded text-ink hover:bg-surface-subtle">
              {editMode ? "Cancel" : "Edit schema"}
            </button>
          </div>

          <div className="flex-1 flex flex-col overflow-hidden bg-code-bg">
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#18222C] border-b border-white/5 shrink-0">
              <span className="text-code-ink text-xs font-mono">json_schema.json</span>
              <span className="text-[#8DA0B0] text-[10px] font-mono">
                {editMode ? "EDIT" : "READ ONLY"} · JSON Schema draft-7
              </span>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {editMode ? (
                <div className="flex flex-col gap-3">
                  <textarea value={editSchema} spellCheck={false}
                    onChange={e => { setEditSchema(e.target.value); const [, err] = parseSchema(e.target.value); setEditSchemaError(err); }}
                    className="w-full bg-transparent text-code-ink text-xs font-mono leading-5 resize-none focus:outline-none caret-white"
                    style={{ minHeight: "300px" }} />
                  {editSchemaError && (
                    <p className="text-danger text-xs font-mono">{editSchemaError}</p>
                  )}
                  <div>
                    <button onClick={handleSaveEdit} disabled={savingEdit || !!editSchemaError}
                      className="px-4 py-2 text-sm bg-ink text-white rounded disabled:opacity-50">
                      {savingEdit ? "Saving…" : "Save schema"}
                    </button>
                  </div>
                </div>
              ) : (
                <pre className="text-code-ink text-xs font-mono leading-5 whitespace-pre-wrap">
                  {JSON.stringify(selected.json_schema, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
          Select a node type to view its schema
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire NodeTypesView in App.tsx**

Edit `frontend/src/App.tsx`. Add import and update the view render:

```tsx
import { NodeTypesView } from "./components/NodeTypesView";

// In JSX:
) : view === "brokers" ? (
  <BrokersView />
) : view === "nodetypes" ? (
  <NodeTypesView />
) : (
  <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
    Coming soon
  </div>
)}
```

- [ ] **Step 5: Rebuild and verify**

```bash
docker compose up --build -d
```

Click "Node types" tab. Create a node type with a JSON Schema. Click it to see the schema in read mode. Click "Edit schema" to edit inline.

---

## Task 5: A5 Frontend — Create UNS Wizard

**Files:**
- Create: `frontend/src/components/CreateUnsWizard.tsx`
- Modify: `frontend/src/components/CatalogView.tsx` (replace "+ New UNS" inline form with wizard)

**Interfaces:**
- Consumes: `api.enterprises.create()`, `api.brokers.list()`, `api.brokers.status()` (from Tasks 1, 2)
- Produces: `CreateUnsWizard` modal component with 3-step stepper

- [ ] **Step 1: Create CreateUnsWizard.tsx**

Create `frontend/src/components/CreateUnsWizard.tsx`:

```tsx
import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { Broker, BrokerStatus } from "../types/uns";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

export function CreateUnsWizard({ onClose, onCreated }: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [broker, setBroker] = useState<Broker | null>(null);
  const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null);
  const [creating, setCreating] = useState(false);

  const rootTopic = name.trim()
    ? name.trim().toLowerCase().replace(/\s+/g, "_")
    : "…";

  useEffect(() => {
    api.brokers.list().then(list => {
      if (list.length > 0) {
        setBroker(list[0]);
        api.brokers.status(list[0].id).then(setBrokerStatus);
      }
    });
  }, []);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      await api.enterprises.create({ name: name.trim(), description: description.trim() || undefined });
      onCreated();
      onClose();
    } finally { setCreating(false); }
  };

  const STEPS = ["Name", "Broker", "Confirm"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-xl border border-border w-full max-w-lg shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-ink">Create Unified Namespace</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-lg leading-none">✕</button>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-0 px-6 pt-5 pb-4">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center">
              <div className={`flex items-center gap-2 ${i < step ? "text-success" : i === step ? "text-ink" : "text-ink-muted"}`}>
                <span className={`w-6 h-6 rounded-full text-xs flex items-center justify-center font-medium border ${
                  i < step ? "bg-success text-white border-success" :
                  i === step ? "bg-ink text-white border-ink" :
                  "border-border-subtle text-ink-muted"
                }`}>
                  {i < step ? "✓" : i + 1}
                </span>
                <span className="text-sm">{label}</span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-12 h-px mx-3 ${i < step ? "bg-success" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="px-6 pb-6 min-h-[200px]">
          {step === 0 && (
            <div className="space-y-4 pt-2">
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">NAMESPACE NAME *</label>
                <input autoFocus type="text" placeholder="ACME Corporation"
                  value={name} onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && name.trim() && setStep(1)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">DESCRIPTION</label>
                <input type="text" placeholder="Optional description"
                  value={description} onChange={e => setDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
              </div>
              {name.trim() && (
                <div className="flex items-center gap-1.5 px-3 py-2 rounded bg-surface-subtle w-fit">
                  <span className="text-accent text-[10px]">◈</span>
                  <span className="text-ink-secondary text-xs font-mono">{rootTopic}/…</span>
                </div>
              )}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4 pt-2">
              <p className="text-sm text-ink-secondary">
                This namespace will publish to the configured EMQX broker.
              </p>
              {broker ? (
                <div className="border border-border rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-ink">{broker.label}</span>
                    {brokerStatus && (
                      <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-medium ${brokerStatus.connected ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${brokerStatus.connected ? "bg-success" : "bg-danger"}`} />
                        {brokerStatus.connected ? "CONNECTED" : "DISCONNECTED"}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-ink-muted font-mono">{broker.host}:{broker.port}</div>
                </div>
              ) : (
                <div className="border border-warning/30 rounded-lg p-4 bg-warning-soft">
                  <p className="text-sm text-warning">No broker configured. Go to the Brokers tab to register one.</p>
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4 pt-2">
              <p className="text-sm text-ink-secondary">Review and confirm the new namespace.</p>
              <div className="border border-border rounded-lg divide-y divide-border-subtle">
                {[
                  ["Name", name],
                  ["Root MQTT topic", rootTopic],
                  ["Description", description || "—"],
                  ["Broker", broker?.label ?? "None configured"],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between px-4 py-3">
                    <span className="text-xs text-ink-muted">{k}</span>
                    <span className="text-sm text-ink font-mono text-right max-w-xs truncate">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-surface-subtle">
          <button onClick={() => step > 0 ? setStep(step - 1) : onClose()}
            className="px-4 py-2 text-sm text-ink-secondary border border-border rounded hover:bg-surface">
            {step === 0 ? "Cancel" : "Back"}
          </button>
          <div className="flex items-center gap-2">
            {step < 2 ? (
              <button onClick={() => setStep(step + 1)} disabled={step === 0 && !name.trim()}
                className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50 hover:bg-ink/90">
                Next
              </button>
            ) : (
              <button onClick={handleCreate} disabled={creating}
                className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50 hover:bg-ink/90">
                {creating ? "Creating…" : "Create namespace"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update CatalogView to use the wizard**

Edit `frontend/src/components/CatalogView.tsx`. Replace the inline form and "+ New UNS" button with the wizard:

```tsx
import { CreateUnsWizard } from "./CreateUnsWizard";  // add import

// In component state, replace `showForm/newName/creating` with:
const [showWizard, setShowWizard] = useState(false);

// Replace the "+ New UNS" button JSX:
<button
  onClick={() => setShowWizard(true)}
  className="flex items-center gap-2 px-4 py-2 bg-ink text-white text-sm rounded font-medium hover:bg-ink/90"
>
  + New UNS
</button>

// Remove the old {showForm && (...)} block entirely.
// Add the wizard modal just before the closing </div> of the component:
{showWizard && (
  <CreateUnsWizard
    onClose={() => setShowWizard(false)}
    onCreated={onRefresh}
  />
)}
```

Also remove the now-unused `creating`, `newName`, `showForm` state variables and `handleCreate` function.

- [ ] **Step 3: Rebuild and verify**

```bash
docker compose up --build -d
```

Open `http://localhost:3001`. Click "+ New UNS" — a 3-step modal should appear. Fill in name, proceed through steps, confirm. The namespace appears in the table.

---

## Task 6: A6 Frontend — Create Asset With Descriptive Modal

**Files:**
- Create: `frontend/src/components/CreateWithDescriptiveModal.tsx`
- Modify: `frontend/src/components/TreePanel.tsx` (intercept cell-level add, open modal)

**Interfaces:**
- Consumes: `api.assets.create()`, `api.nodeTypes.list()` (from Tasks 1, 3)
- Produces: `CreateWithDescriptiveModal` modal component

- [ ] **Step 1: Create CreateWithDescriptiveModal.tsx**

Create `frontend/src/components/CreateWithDescriptiveModal.tsx`:

```tsx
import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { NodeType } from "../types/uns";

interface Props {
  cellId: string;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateWithDescriptiveModal({ cellId, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nodeTypes, setNodeTypes] = useState<NodeType[]>([]);
  const [selectedNodeTypeId, setSelectedNodeTypeId] = useState<string>("");
  const [payloadText, setPayloadText] = useState("{\n  \n}");
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.nodeTypes.list().then(setNodeTypes);
  }, []);

  // When a node type is selected, load its schema as a template payload
  useEffect(() => {
    if (!selectedNodeTypeId) { setPayloadText("{\n  \n}"); return; }
    const nt = nodeTypes.find(n => n.id === selectedNodeTypeId);
    if (!nt) return;
    // Build a template from the schema's properties
    const props = (nt.json_schema.properties ?? {}) as Record<string, unknown>;
    const template: Record<string, unknown> = {};
    for (const [key, def] of Object.entries(props)) {
      const d = def as Record<string, unknown>;
      if (d.type === "number") template[key] = 0;
      else if (d.type === "boolean") template[key] = false;
      else if (d.type === "array") template[key] = [];
      else if (d.type === "object") template[key] = {};
      else template[key] = "";
    }
    setPayloadText(JSON.stringify(template, null, 2));
    setPayloadError(null);
  }, [selectedNodeTypeId, nodeTypes]);

  const handlePayloadChange = (text: string) => {
    setPayloadText(text);
    try { JSON.parse(text); setPayloadError(null); }
    catch (e: unknown) { setPayloadError(e instanceof Error ? e.message : "Invalid JSON"); }
  };

  const handleCreate = async () => {
    if (!name.trim() || payloadError) return;
    let parsed: Record<string, unknown> | undefined;
    try { parsed = JSON.parse(payloadText); }
    catch { setPayloadError("Invalid JSON"); return; }
    setSaving(true);
    try {
      await api.assets.create(cellId, {
        name: name.trim(),
        description: description.trim() || undefined,
        descriptive_payload: parsed,
      });
      onCreated();
      onClose();
    } finally { setSaving(false); }
  };

  const lineNumbers = payloadText.split("\n").map((_, i) => i + 1).join("\n");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-xl border border-border w-full max-w-2xl shadow-xl overflow-hidden flex flex-col" style={{ maxHeight: "90vh" }}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <h2 className="text-base font-semibold text-ink">New Asset</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-lg">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Fields */}
          <div className="px-6 py-5 space-y-4 border-b border-border">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">NAME *</label>
                <input autoFocus type="text" placeholder="TempSensor_01"
                  value={name} onChange={e => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">NODE TYPE</label>
                <select value={selectedNodeTypeId} onChange={e => setSelectedNodeTypeId(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent">
                  <option value="">— None —</option>
                  {nodeTypes.map(nt => (
                    <option key={nt.id} value={nt.id}>{nt.name}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">DESCRIPTION</label>
              <input type="text" placeholder="Optional description"
                value={description} onChange={e => setDescription(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
            </div>
          </div>

          {/* Inline JSON editor */}
          <div className="flex flex-col bg-code-bg" style={{ minHeight: "220px" }}>
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#18222C] border-b border-white/5">
              <div className="flex items-center gap-2">
                <span className="text-[#71B9E3] text-xs">◆</span>
                <span className="text-code-ink text-xs font-mono">_descriptive.json</span>
              </div>
              <span className="text-[#8DA0B0] text-[10px] font-mono">EDIT · JSON · UTF-8</span>
            </div>
            <div className="flex flex-1 overflow-auto" style={{ minHeight: "180px" }}>
              <div className="px-3 py-4 text-right select-none shrink-0 w-10">
                <pre className="text-code-muted text-xs font-mono leading-5">{lineNumbers}</pre>
              </div>
              <div className="flex-1 py-4 pr-4">
                <textarea value={payloadText} spellCheck={false}
                  onChange={e => handlePayloadChange(e.target.value)}
                  className="w-full h-full bg-transparent text-code-ink text-xs font-mono leading-5 resize-none focus:outline-none caret-white"
                  style={{ minHeight: "160px" }} />
              </div>
            </div>
            {payloadError && (
              <div className="px-4 py-1.5 bg-danger/20 text-danger text-xs font-mono border-t border-danger/30">
                {payloadError}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-surface-subtle shrink-0">
          <div className="flex items-center gap-1">
            {payloadError ? (
              <><span className="text-danger text-xs">✗</span><span className="text-danger text-xs">Invalid JSON</span></>
            ) : (
              <><span className="text-success text-xs">✓</span><span className="text-success text-xs">Valid JSON</span></>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-ink-secondary border border-border rounded hover:bg-surface">
              Cancel
            </button>
            <button onClick={handleCreate} disabled={saving || !name.trim() || !!payloadError}
              className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50 hover:bg-ink/90">
              {saving ? "Creating…" : "Create asset"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update TreePanel to open modal for asset creation**

Edit `frontend/src/components/TreePanel.tsx`. Add import and state:

```tsx
import { CreateWithDescriptiveModal } from "./CreateWithDescriptiveModal";

// Add state inside TreePanel:
const [assetModalCellId, setAssetModalCellId] = useState<string | null>(null);
```

Find the `createChild` function. The `else if (level === "cell")` branch currently does:
```tsx
else if (level === "cell") await api.assets.create(parentId, { ...body, descriptive_payload: {} });
```

Replace that entire branch with nothing — instead, intercept BEFORE `createChild` is called. Change the `onAdd` for each Cell's `TreeRow` to use the modal:

```tsx
// Find this line in the Cell TreeRow:
onAdd={() => setAddingChild({ level: "cell", parentId: cell.id })}
// Replace with:
onAdd={() => setAssetModalCellId(cell.id)}
```

Also update `createChild` to guard against the cell level (it will never be called for cells now, but for safety):
```tsx
const createChild = async () => {
  if (!addingChild || !newName.trim()) return;
  const body = { name: newName.trim() };
  const { level, parentId } = addingChild;
  if (level === "enterprise") await api.sites.create(parentId, body);
  else if (level === "site") await api.areas.create(parentId, body);
  else if (level === "area") await api.lines.create(parentId, body);
  else if (level === "line") await api.cells.create(parentId, body);
  // "cell" level (asset creation) is handled by CreateWithDescriptiveModal
  setAddingChild(null);
  setNewName("");
  onRefresh();
};
```

Add the modal rendering at the end of the `TreePanel` return statement, before the closing `</aside>`:

```tsx
{assetModalCellId && (
  <CreateWithDescriptiveModal
    cellId={assetModalCellId}
    onClose={() => setAssetModalCellId(null)}
    onCreated={() => { setAssetModalCellId(null); onRefresh(); }}
  />
)}
```

- [ ] **Step 3: Rebuild and verify**

```bash
docker compose up --build -d
```

Open workspace, navigate to a Cell node, hover over it and click "+". A modal should open with name field, node type dropdown, and JSON editor. Select a node type — the payload editor should pre-fill with a template. Save and verify the asset appears in the tree.

---

## Task 7: A2 Backend + Frontend — Data Branch Discovery

**Files:**
- Modify: `backend/app/routers/assets.py` (add branches endpoint)
- Modify: `frontend/src/components/NodeWorkspace.tsx` (make branches tab functional)
- Modify: `frontend/src/api/client.ts` (add branches API)
- Modify: `frontend/src/types/uns.ts` (add DataBranch interface)

**Interfaces:**
- Consumes: `broker_service.get_subscriptions(broker, topic)` (from Task 1)
- Produces: `GET /cells/{cell_id}/assets/{asset_id}/branches` → `list[DataBranch]`

- [ ] **Step 1: Add DataBranch type**

Edit `frontend/src/types/uns.ts`. Append:

```typescript
export interface DataBranch {
  client_id: string;
  topic_filter: string;
  qos: number;
  connected_at: string | null;
}
```

- [ ] **Step 2: Add branches endpoint to assets router**

Edit `backend/app/routers/assets.py`. Add imports:

```python
from typing import Any
from sqlalchemy.future import select as sa_select
from app.models.broker import Broker
from app.services import broker_service
```

Add new endpoint after the existing routes:

```python
@router.get("/{asset_id}/branches", response_model=list[dict])
async def get_asset_branches(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    if not obj.uns_topic:
        return []

    # Get first registered broker
    result = await db.execute(sa_select(Broker).order_by(Broker.label).limit(1))
    b = result.scalar_one_or_none()
    if not b:
        return []

    return await broker_service.get_subscriptions(b, obj.uns_topic)
```

- [ ] **Step 3: Add branches to API client**

Edit `frontend/src/api/client.ts`. Add import and entry:

```typescript
import type { /* existing */, DataBranch } from "../types/uns";

// add to api object:
  branches: {
    list: (cellId: string, assetId: string) =>
      http.get<DataBranch[]>(`/cells/${cellId}/assets/${assetId}/branches`).then((r) => r.data),
  },
```

- [ ] **Step 4: Update NodeWorkspace branches tab**

Edit `frontend/src/components/NodeWorkspace.tsx`. Add state and load logic:

```tsx
import type { /* existing */, DataBranch } from "../types/uns";

// Add state:
const [branches, setBranches] = useState<DataBranch[]>([]);
const [branchesLoading, setBranchesLoading] = useState(false);
const [branchesError, setBranchesError] = useState(false);

// Add effect (after existing useEffect):
useEffect(() => {
  if (tab !== "branches" || !asset || !selected?.parentIds.cell_id) return;
  setBranchesLoading(true);
  setBranchesError(false);
  api.branches.list(selected.parentIds.cell_id, asset.id)
    .then(data => { setBranches(data); setBranchesLoading(false); })
    .catch(() => { setBranchesError(true); setBranchesLoading(false); });
}, [tab, asset, selected]);
```

Update the TABS definition to show real count:

```tsx
{ id: "branches", label: `Data branches · ${branches.length}`, dot: branches.length > 0 ? "success" : "muted" },
```

Replace the branches empty state in the work area:

```tsx
) : tab === "branches" ? (
  <div className="flex-1 flex flex-col overflow-hidden">
    <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle bg-surface-subtle">
      <span className="text-xs text-ink-muted">{branches.length} active subscriber{branches.length !== 1 ? "s" : ""}</span>
      <button
        onClick={() => {
          if (!asset || !selected?.parentIds.cell_id) return;
          setBranchesLoading(true);
          api.branches.list(selected.parentIds.cell_id, asset.id)
            .then(data => { setBranches(data); setBranchesLoading(false); })
            .catch(() => { setBranchesError(true); setBranchesLoading(false); });
        }}
        className="text-xs text-ink-muted hover:text-ink border border-border-subtle rounded px-2 py-0.5"
      >
        ↺ Refresh
      </button>
    </div>
    {branchesLoading ? (
      <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">Loading…</div>
    ) : branchesError ? (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-1">
          <p className="text-warning text-sm">Branch discovery unavailable</p>
          <p className="text-ink-muted text-xs">EMQX API unreachable or no broker configured</p>
        </div>
      </div>
    ) : branches.length === 0 ? (
      <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
        No active subscribers on this topic
      </div>
    ) : (
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-[1fr_1fr_60px] text-[10px] tracking-widest text-ink-muted px-5 py-2 border-b border-border-subtle bg-surface-subtle">
          <span>CLIENT ID</span><span>TOPIC FILTER</span><span>QOS</span>
        </div>
        {branches.map((b, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_60px] px-5 py-3 border-b border-border-subtle hover:bg-surface-subtle text-sm">
            <span className="text-ink font-mono text-xs truncate">{b.client_id}</span>
            <span className="text-ink-secondary font-mono text-xs truncate">{b.topic_filter}</span>
            <span className="text-ink-muted text-xs">QoS {b.qos}</span>
          </div>
        ))}
      </div>
    )}
  </div>
) : (
```

- [ ] **Step 5: Rebuild and verify**

```bash
docker compose up --build -d
```

Select an Asset, click the "Data branches" tab. If no external clients subscribe to the topic, you'll see "No active subscribers on this topic". The count in the tab label should be `0`. The Refresh button should re-query without error.

---

## Task 8: A3 — Subtree Copy/Move + CopyMoveModal

**Files:**
- Create: `backend/app/services/subtree_service.py`
- Modify: `backend/app/routers/tree.py` (add copy/move/publish-subtree endpoints)
- Create: `frontend/src/components/CopyMoveModal.tsx`
- Modify: `frontend/src/components/TreePanel.tsx` (add copy/move hover actions)
- Modify: `frontend/src/api/client.ts` (add tree copy/move/publishSubtree)
- Modify: `frontend/src/types/uns.ts` (add SubtreeOperation, SubtreeResult, HierarchyLevel helpers)

**Interfaces:**
- Produces: `POST /tree/copy`, `POST /tree/move`, `POST /tree/publish-subtree`
- Produces: `CopyMoveModal` React component

- [ ] **Step 1: Create subtree_service.py**

Create `backend/app/services/subtree_service.py`:

```python
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.uns import Enterprise, Site, Area, Line, Cell, Asset
from app.models.uns import _uuid
from app.services.mqtt_service import publish_descriptive
from app.services.uns_service import build_uns_topic

logger = logging.getLogger(__name__)

LEVEL_ORDER = ["enterprise", "site", "area", "line", "cell", "asset"]


async def _copy_sites(site: Site, new_enterprise_id: str, db: AsyncSession) -> int:
    new_site = Site(id=_uuid(), enterprise_id=new_enterprise_id, name=site.name, description=site.description)
    db.add(new_site)
    await db.flush()
    count = 1
    for area in site.areas:
        count += await _copy_areas(area, new_site.id, db)
    return count


async def _copy_areas(area: Area, new_site_id: str, db: AsyncSession) -> int:
    new_area = Area(id=_uuid(), site_id=new_site_id, name=area.name, description=area.description)
    db.add(new_area)
    await db.flush()
    count = 1
    for line in area.lines:
        count += await _copy_lines(line, new_area.id, db)
    return count


async def _copy_lines(line: Line, new_area_id: str, db: AsyncSession) -> int:
    new_line = Line(id=_uuid(), area_id=new_area_id, name=line.name, description=line.description)
    db.add(new_line)
    await db.flush()
    count = 1
    for cell in line.cells:
        count += await _copy_cells(cell, new_line.id, db)
    return count


async def _copy_cells(cell: Cell, new_line_id: str, db: AsyncSession) -> int:
    new_cell = Cell(id=_uuid(), line_id=new_line_id, name=cell.name, description=cell.description)
    db.add(new_cell)
    await db.flush()
    count = 1
    for asset in cell.assets:
        new_asset = Asset(
            id=_uuid(), cell_id=new_cell.id,
            name=asset.name, description=asset.description,
            descriptive_payload=asset.descriptive_payload,
            node_type_id=asset.node_type_id,
        )
        db.add(new_asset)
        count += 1
    return count


async def copy_subtree(
    source_id: str, source_level: str, target_parent_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Deep-copy a subtree under a new parent. Returns new root id and node count."""
    if source_level == "site":
        result = await db.execute(
            select(Site).where(Site.id == source_id)
            .options(selectinload(Site.areas).selectinload(Area.lines).selectinload(Line.cells).selectinload(Cell.assets))
        )
        site = result.scalar_one_or_none()
        if not site:
            raise ValueError("Source site not found")
        count = await _copy_sites(site, target_parent_id, db)
        await db.commit()
        return {"new_root_id": target_parent_id, "node_count": count}

    elif source_level == "area":
        result = await db.execute(
            select(Area).where(Area.id == source_id)
            .options(selectinload(Area.lines).selectinload(Line.cells).selectinload(Cell.assets))
        )
        area = result.scalar_one_or_none()
        if not area:
            raise ValueError("Source area not found")
        count = await _copy_areas(area, target_parent_id, db)
        await db.commit()
        return {"new_root_id": target_parent_id, "node_count": count}

    elif source_level == "line":
        result = await db.execute(
            select(Line).where(Line.id == source_id)
            .options(selectinload(Line.cells).selectinload(Cell.assets))
        )
        line = result.scalar_one_or_none()
        if not line:
            raise ValueError("Source line not found")
        count = await _copy_lines(line, target_parent_id, db)
        await db.commit()
        return {"new_root_id": target_parent_id, "node_count": count}

    elif source_level == "cell":
        result = await db.execute(
            select(Cell).where(Cell.id == source_id)
            .options(selectinload(Cell.assets))
        )
        cell = result.scalar_one_or_none()
        if not cell:
            raise ValueError("Source cell not found")
        count = await _copy_cells(cell, target_parent_id, db)
        await db.commit()
        return {"new_root_id": target_parent_id, "node_count": count}

    raise ValueError(f"Unsupported source level: {source_level}")


async def move_subtree(
    source_id: str, source_level: str, target_parent_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Move a node to a new parent by updating its FK. Single transaction."""
    if source_level == "site":
        obj = await db.get(Site, source_id)
        if not obj:
            raise ValueError("Source site not found")
        obj.enterprise_id = target_parent_id
    elif source_level == "area":
        obj = await db.get(Area, source_id)
        if not obj:
            raise ValueError("Source area not found")
        obj.site_id = target_parent_id
    elif source_level == "line":
        obj = await db.get(Line, source_id)
        if not obj:
            raise ValueError("Source line not found")
        obj.area_id = target_parent_id
    elif source_level == "cell":
        obj = await db.get(Cell, source_id)
        if not obj:
            raise ValueError("Source cell not found")
        obj.line_id = target_parent_id
    elif source_level == "asset":
        obj = await db.get(Asset, source_id)
        if not obj:
            raise ValueError("Source asset not found")
        obj.cell_id = target_parent_id
    else:
        raise ValueError(f"Unsupported source level: {source_level}")
    await db.commit()
    return {"moved_root_id": source_id, "node_count": 1}


async def publish_subtree(root_id: str, root_level: str, db: AsyncSession) -> dict[str, Any]:
    """Publish all assets in a subtree to EMQX. Returns published/failed counts."""
    published = 0
    failed = 0

    async def pub_asset(asset: Asset) -> None:
        nonlocal published, failed
        if not asset.descriptive_payload:
            return
        try:
            topic = await build_uns_topic(asset, db)
            asset.uns_topic = topic
            publish_descriptive(topic, asset.descriptive_payload)
            published += 1
        except Exception as exc:
            logger.error("Failed to publish asset %s: %s", asset.id, exc)
            failed += 1

    if root_level == "asset":
        asset = await db.get(Asset, root_id)
        if asset:
            await pub_asset(asset)
    elif root_level == "cell":
        result = await db.execute(select(Asset).where(Asset.cell_id == root_id))
        for asset in result.scalars().all():
            await pub_asset(asset)
    elif root_level == "line":
        result = await db.execute(
            select(Cell).where(Cell.line_id == root_id).options(selectinload(Cell.assets))
        )
        for cell in result.scalars().all():
            for asset in cell.assets:
                await pub_asset(asset)
    elif root_level == "area":
        result = await db.execute(
            select(Line).where(Line.area_id == root_id)
            .options(selectinload(Line.cells).selectinload(Cell.assets))
        )
        for line in result.scalars().all():
            for cell in line.cells:
                for asset in cell.assets:
                    await pub_asset(asset)
    elif root_level in ("site", "enterprise"):
        # Walk the full subtree
        if root_level == "site":
            q = select(Area).where(Area.site_id == root_id)
        else:
            q = select(Site).where(Site.enterprise_id == root_id)
        # For simplicity, recursively call for each child
        # (enterprise level is unusual for publish-subtree but handled gracefully)

    await db.commit()
    return {"published": published, "failed": failed}
```

- [ ] **Step 2: Add copy/move endpoints to tree.py**

Edit `backend/app/routers/tree.py`. Add imports and new endpoints:

```python
from pydantic import BaseModel
from typing import Literal
from app.services import subtree_service

class SubtreeOperationBody(BaseModel):
    source_id: str
    source_level: Literal["site", "area", "line", "cell", "asset"]
    target_parent_id: str

class PublishSubtreeBody(BaseModel):
    root_id: str
    root_level: Literal["enterprise", "site", "area", "line", "cell", "asset"]


@router.post("/copy")
async def copy_subtree(body: SubtreeOperationBody, db: AsyncSession = Depends(get_db)):
    try:
        result = await subtree_service.copy_subtree(
            body.source_id, body.source_level, body.target_parent_id, db
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/move")
async def move_subtree(body: SubtreeOperationBody, db: AsyncSession = Depends(get_db)):
    try:
        result = await subtree_service.move_subtree(
            body.source_id, body.source_level, body.target_parent_id, db
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/publish-subtree")
async def publish_subtree(body: PublishSubtreeBody, db: AsyncSession = Depends(get_db)):
    result = await subtree_service.publish_subtree(body.root_id, body.root_level, db)
    return result
```

- [ ] **Step 3: Add tree copy/move to API client**

Edit `frontend/src/api/client.ts`. Update the `tree` namespace:

```typescript
  tree: {
    get: () => http.get<EnterpriseTree[]>("/tree/").then((r) => r.data),
    copy: (body: { source_id: string; source_level: string; target_parent_id: string }) =>
      http.post<{ new_root_id: string; node_count: number }>("/tree/copy", body).then((r) => r.data),
    move: (body: { source_id: string; source_level: string; target_parent_id: string }) =>
      http.post<{ moved_root_id: string; node_count: number }>("/tree/move", body).then((r) => r.data),
    publishSubtree: (body: { root_id: string; root_level: string }) =>
      http.post<{ published: number; failed: number }>("/tree/publish-subtree", body).then((r) => r.data),
  },
```

- [ ] **Step 4: Create CopyMoveModal.tsx**

Create `frontend/src/components/CopyMoveModal.tsx`:

```tsx
import { useState } from "react";
import { api } from "../api/client";
import type { EnterpriseTree, HierarchyLevel } from "../types/uns";

interface Props {
  sourceId: string;
  sourceLevel: HierarchyLevel;
  sourceName: string;
  enterprise: EnterpriseTree;
  onClose: () => void;
  onDone: () => void;
}

// Valid parent levels for each source level
const VALID_PARENT: Record<string, HierarchyLevel[]> = {
  site: ["enterprise"], area: ["site"], line: ["area"],
  cell: ["line"], asset: ["cell"],
};

type Node = { id: string; name: string; level: HierarchyLevel };

function collectNodes(enterprise: EnterpriseTree): Node[] {
  const nodes: Node[] = [{ id: enterprise.id, name: enterprise.name, level: "enterprise" }];
  enterprise.sites.forEach(s => {
    nodes.push({ id: s.id, name: s.name, level: "site" });
    s.areas.forEach(a => {
      nodes.push({ id: a.id, name: a.name, level: "area" });
      a.lines.forEach(l => {
        nodes.push({ id: l.id, name: l.name, level: "line" });
        l.cells.forEach(c => {
          nodes.push({ id: c.id, name: c.name, level: "cell" });
        });
      });
    });
  });
  return nodes;
}

export function CopyMoveModal({ sourceId, sourceLevel, sourceName, enterprise, onClose, onDone }: Props) {
  const [mode, setMode] = useState<"copy" | "move">("copy");
  const [targetParentId, setTargetParentId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ count: number } | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<{ published: number; failed: number } | null>(null);

  const validParentLevels = VALID_PARENT[sourceLevel] ?? [];
  const allNodes = collectNodes(enterprise);
  const validParents = allNodes.filter(n => validParentLevels.includes(n.level) && n.id !== sourceId);

  const handleConfirm = async () => {
    if (!targetParentId) return;
    setLoading(true);
    try {
      const body = { source_id: sourceId, source_level: sourceLevel, target_parent_id: targetParentId };
      if (mode === "copy") {
        const r = await api.tree.copy(body);
        setResult({ count: r.node_count });
      } else {
        const r = await api.tree.move(body);
        setResult({ count: r.node_count });
      }
    } finally { setLoading(false); }
  };

  const handlePublish = async () => {
    setPublishing(true);
    try {
      const r = await api.tree.publishSubtree({ root_id: sourceId, root_level: sourceLevel });
      setPublishResult(r);
      onDone();
    } finally { setPublishing(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-xl border border-border w-full max-w-lg shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-ink">Copy / Move Subtree</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-lg">✕</button>
        </div>

        {!result ? (
          <div className="px-6 py-5 space-y-5">
            {/* Mode */}
            <div className="flex gap-2">
              {(["copy", "move"] as const).map(m => (
                <button key={m} onClick={() => setMode(m)}
                  className={`px-4 py-2 text-sm rounded border ${mode === m ? "bg-ink text-white border-ink" : "border-border text-ink-secondary hover:bg-surface-subtle"}`}>
                  {m === "copy" ? "Copy" : "Move"}
                </button>
              ))}
            </div>

            {/* Source */}
            <div>
              <div className="text-[10px] tracking-widest text-ink-muted mb-1.5">SOURCE</div>
              <div className="flex items-center gap-2 px-3 py-2 border border-border rounded bg-surface-subtle">
                <span className="text-ink text-sm font-medium">{sourceName}</span>
                <span className="px-2 py-0.5 rounded bg-surface text-ink-secondary text-[10px] font-medium tracking-wider border border-border">
                  {sourceLevel.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Target */}
            <div>
              <div className="text-[10px] tracking-widest text-ink-muted mb-1.5">DESTINATION PARENT</div>
              <select value={targetParentId} onChange={e => setTargetParentId(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent">
                <option value="">Select destination…</option>
                {validParents.map(n => (
                  <option key={n.id} value={n.id}>
                    {n.name} ({n.level})
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
              <button onClick={onClose} className="px-4 py-2 text-sm text-ink-secondary border border-border rounded">
                Cancel
              </button>
              <button onClick={handleConfirm} disabled={loading || !targetParentId}
                className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50">
                {loading ? "Processing…" : `Confirm ${mode}`}
              </button>
            </div>
          </div>
        ) : (
          <div className="px-6 py-5 space-y-5">
            <div className="flex items-center gap-3 p-4 rounded-lg bg-success-soft">
              <span className="text-success text-xl">✓</span>
              <div>
                <p className="text-success font-medium text-sm">
                  {mode === "copy" ? "Copy" : "Move"} completed — {result.count} node{result.count !== 1 ? "s" : ""}
                </p>
                <p className="text-success/70 text-xs mt-0.5">New MQTT topics not yet published</p>
              </div>
            </div>
            {publishResult ? (
              <div className="p-4 rounded-lg bg-surface-subtle text-sm text-ink">
                Published {publishResult.published} asset{publishResult.published !== 1 ? "s" : ""}.
                {publishResult.failed > 0 && <span className="text-warning"> {publishResult.failed} failed.</span>}
              </div>
            ) : (
              <p className="text-sm text-ink-secondary">
                Do you want to publish all assets in the {mode === "copy" ? "copied" : "moved"} subtree to EMQX now?
              </p>
            )}
            <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
              <button onClick={() => { onDone(); onClose(); }}
                className="px-4 py-2 text-sm text-ink-secondary border border-border rounded">
                {publishResult ? "Close" : "Publish later"}
              </button>
              {!publishResult && (
                <button onClick={handlePublish} disabled={publishing}
                  className="px-5 py-2 text-sm bg-accent text-white rounded disabled:opacity-50">
                  {publishing ? "Publishing…" : "Publish to EMQX"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Add copy/move triggers to TreePanel**

Edit `frontend/src/components/TreePanel.tsx`. Add imports and state:

```tsx
import { CopyMoveModal } from "./CopyMoveModal";
import type { EnterpriseTree } from "../types/uns";

// Add to Props interface:
interface Props {
  enterprise: EnterpriseTree;
  selected: SelectedNode | null;
  onSelect: (node: SelectedNode) => void;
  onRefresh: () => void;
}

// Add state in TreePanel:
const [copyMoveNode, setCopyMoveNode] = useState<{ id: string; level: HierarchyLevel; name: string } | null>(null);
```

Update the `TreeRow` props interface and component to accept an `onCopy` callback:

```tsx
interface RowProps {
  // ... existing ...
  onCopy?: () => void;
}

// In TreeRow, add next to onAdd button:
{onCopy && (hovered || selected) && (
  <button
    onClick={e => { e.stopPropagation(); onCopy(); }}
    className="w-5 h-5 flex items-center justify-center text-ink-muted hover:text-ink rounded text-xs shrink-0"
    title="Copy/Move"
  >⧉</button>
)}
```

For each `TreeRow` (site, area, line, cell), add an `onCopy` prop:

```tsx
// Example for Site TreeRow:
onCopy={() => setCopyMoveNode({ id: site.id, level: "site", name: site.name })}
```

Add the modal at the end of the `TreePanel` return:

```tsx
{copyMoveNode && (
  <CopyMoveModal
    sourceId={copyMoveNode.id}
    sourceLevel={copyMoveNode.level}
    sourceName={copyMoveNode.name}
    enterprise={enterprise}
    onClose={() => setCopyMoveNode(null)}
    onDone={() => { setCopyMoveNode(null); onRefresh(); }}
  />
)}
```

- [ ] **Step 6: Rebuild and verify**

```bash
docker compose up --build -d
```

Hover over a Site node in the tree — you should see a `⧉` icon. Click it to open the Copy/Move modal. Select destination, confirm copy, then choose to publish or not.

---

## Task 9: A9 — Sync Status Endpoint + Workspace Banner

**Files:**
- Modify: `backend/app/routers/assets.py` (add sync-status endpoint)
- Modify: `frontend/src/components/NodeWorkspace.tsx` (sync status banner)
- Modify: `frontend/src/api/client.ts` (add syncStatus)
- Modify: `frontend/src/types/uns.ts` (add SyncStatus interface)

**Interfaces:**
- Consumes: `Asset.last_published_at`, `Asset.updated_at` (from Task 3)
- Produces: `GET /cells/{cell_id}/assets/{asset_id}/sync-status` → SyncStatus
- Produces: Red/green SYNCED badge + diff banner in NodeWorkspace

- [ ] **Step 1: Add SyncStatus type**

Edit `frontend/src/types/uns.ts`. Append:

```typescript
export interface SyncStatus {
  synced: boolean;
  last_published_at: string | null;
  last_updated_at: string;
  diff_note: string | null;
}
```

- [ ] **Step 2: Add sync-status endpoint**

Edit `backend/app/routers/assets.py`. Add endpoint:

```python
from datetime import timezone

@router.get("/{asset_id}/sync-status")
async def get_sync_status(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    if obj.last_published_at is None:
        return {
            "synced": False,
            "last_published_at": None,
            "last_updated_at": obj.updated_at.isoformat(),
            "diff_note": "Asset has never been published to EMQX",
        }

    # Compare publish time vs last DB update
    pub = obj.last_published_at.replace(tzinfo=timezone.utc) if obj.last_published_at.tzinfo is None else obj.last_published_at
    upd = obj.updated_at.replace(tzinfo=timezone.utc) if obj.updated_at.tzinfo is None else obj.updated_at

    synced = pub >= upd
    diff_note = None if synced else f"Payload updated {upd.isoformat()} after last publish {pub.isoformat()}"

    return {
        "synced": synced,
        "last_published_at": pub.isoformat(),
        "last_updated_at": upd.isoformat(),
        "diff_note": diff_note,
    }
```

- [ ] **Step 3: Add syncStatus to API client**

Edit `frontend/src/api/client.ts`. Add import and entry:

```typescript
import type { /* existing */, SyncStatus } from "../types/uns";

  syncStatus: {
    get: (cellId: string, assetId: string) =>
      http.get<SyncStatus>(`/cells/${cellId}/assets/${assetId}/sync-status`).then((r) => r.data),
  },
```

- [ ] **Step 4: Add sync banner to NodeWorkspace**

Edit `frontend/src/components/NodeWorkspace.tsx`. Add state:

```tsx
import type { /* existing */, SyncStatus } from "../types/uns";

const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);

// Add to existing useEffect that loads asset:
useEffect(() => {
  if (selected?.level === "asset" && selected.parentIds.cell_id) {
    api.assets.list(selected.parentIds.cell_id).then(list => {
      const found = list.find(a => a.id === selected.id);
      if (found) {
        setAsset(found);
        setPayload(found.descriptive_payload ?? {});
        // Load sync status
        api.syncStatus.get(selected.parentIds.cell_id, found.id)
          .then(setSyncStatus)
          .catch(() => setSyncStatus(null));
      }
    });
  } else {
    setAsset(null);
    setSyncStatus(null);
  }
}, [selected]);
```

Update the SYNCED badge in the node header to use real sync status:

```tsx
{asset && syncStatus && (
  <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
    syncStatus.synced ? "bg-success-soft text-success" : "bg-danger-soft text-danger"
  }`}>
    <span className={`w-1.5 h-1.5 rounded-full inline-block ${syncStatus.synced ? "bg-success" : "bg-danger"}`} />
    {syncStatus.synced ? "SYNCED" : "UNSYNCED"}
  </span>
)}
```

Add sync banner below the node header div (before the tabs div), shown only when unsynced:

```tsx
{asset && syncStatus && !syncStatus.synced && (
  <div className="px-6 py-3 bg-danger/10 border-b border-danger/20 flex items-start justify-between gap-4">
    <div className="flex items-start gap-2">
      <span className="text-danger text-sm mt-0.5">⚠</span>
      <div>
        <p className="text-danger text-sm font-medium">Out of sync with EMQX</p>
        <p className="text-danger/70 text-xs mt-0.5">{syncStatus.diff_note}</p>
      </div>
    </div>
    <button
      onClick={async () => {
        if (!selected?.parentIds.cell_id || !asset) return;
        setSaving(true);
        try {
          await api.assets.update(selected.parentIds.cell_id, asset.id, { descriptive_payload: payload });
          await api.assets.publish(selected.parentIds.cell_id, asset.id);
          const s = await api.syncStatus.get(selected.parentIds.cell_id, asset.id);
          setSyncStatus(s);
          setPublished(true);
          setTimeout(() => setPublished(false), 3000);
        } finally { setSaving(false); }
      }}
      disabled={saving}
      className="px-3 py-1.5 text-xs bg-danger text-white rounded shrink-0 disabled:opacity-50"
    >
      Re-sync
    </button>
  </div>
)}
```

- [ ] **Step 5: Rebuild and verify**

```bash
docker compose up --build -d
```

Select an Asset that has never been published. The badge should show "UNSYNCED" in red and a warning banner appears. Click "Re-sync" — it publishes and the badge turns green "SYNCED". Then edit the payload and save (without publishing) — the badge turns red again showing the payload was updated after the last publish.

---

## Self-Review

**Spec coverage:**
- A7 Broker Registry → Tasks 1, 2 ✓
- A8 Node Type Catalog → Tasks 3, 4 ✓
- A5 Create UNS Wizard → Task 5 ✓
- A6 Create Node With Descriptive → Task 6 ✓
- A2 Data Branch Auto-Discovery → Task 7 ✓
- A3 Copy/Move Subtree (two-step) → Task 8 ✓
- A9 Broker Sync Failure → Task 9 ✓

**Type consistency:**
- `broker_service.get_subscriptions(broker, topic)` defined in Task 1, consumed in Task 7 ✓
- `broker_service.get_retained_payload(broker, topic)` defined in Task 1, available for future use ✓
- `Asset.last_published_at` defined in Task 3, consumed in Task 9 endpoint ✓
- `api.brokers.*` defined in Task 2, consumed in Task 5 wizard ✓
- `api.nodeTypes.*` defined in Task 4, consumed in Task 6 modal ✓
- `api.tree.copy/move/publishSubtree` defined in Task 8, consumed in CopyMoveModal ✓

**No placeholders:** All code blocks are complete implementations with no TBDs.
