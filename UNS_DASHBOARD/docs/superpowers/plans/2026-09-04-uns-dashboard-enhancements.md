# UNS Dashboard Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four enhancements from `docs/superpowers/specs/2026-09-04-uns-dashboard-enhancements-design.md`: a hierarchical, dual-source signal picker; a real chart-color system plus the ability to edit an existing chart; an ECharts migration giving the timeseries chart native zoom; and frontend-visible degraded-mode UX when streaming or the Historian is unreachable.

**Architecture:** Backend gains two new signal-discovery endpoints (Historian-backed tree for historical charts, Redis-backed tree for live charts) built on one pure tree-builder; the bridge additionally forwards `_analytical` topics. Frontend gains two small pure `lib/` modules (color resolution, connection-state), a new hierarchical picker component replacing the flat one, edit-mode wiring through `ChartForm`/`ChartCardShell`/`EditorPage`, and an ECharts-based rewrite of the three genuinely chart-shaped components (timeseries/gauge/bar) — KPI/status/table stay plain React by design.

**Tech Stack:** FastAPI + SQLAlchemy async + Redis (`redis.asyncio`) on the backend; React + TypeScript + `echarts`/`echarts-for-react` (replacing `recharts`) on the frontend; `pytest`/`pytest-asyncio` and `vitest`/`@testing-library/react`.

## Global Constraints

- No new native dependencies for chart testing — ECharts instances use `opts={{ renderer: "svg" }}` everywhere so jsdom needs no canvas shim.
- KPI tile, status indicator, and values table are explicitly **not** migrated to ECharts (design spec Section 3) — they stay plain React/HTML.
- `/signals/catalog` and `SignalPicker.tsx` are retired outright, not kept for backward compatibility.
- Color resolution is one function used everywhere (design spec Section 2): `signal.color` override → else `chart.color` if the chart has exactly one signal → else a rotating palette by signal index.
- Staleness threshold for live charts: 15 seconds since the freshest frame (or since connecting, if none has arrived yet).
- Testing philosophy carried over from v1: pure logic gets full unit coverage with no live services; thin async I/O glue (Redis `SCAN`/`XREVRANGE`, the WebSocket itself) is verified manually/live only; tests touching a real Postgres are gated with `pytest.mark.skipif` on the relevant `*_DATABASE_URL` env var, exactly like the existing `test_signals_router.py`/`test_charts_router.py`.
- Follow existing code conventions exactly (see any file in `backend/app/routers/` or `frontend/src/components/`) — no reformatting, no unrelated refactors.

---

## File Structure

**Backend — new:**
- `backend/app/services/signal_tree.py` — pure topic-list → nested-tree builder, plus `topic_type_of`.
- `backend/app/services/live_topics.py` — Redis `SCAN`/`XREVRANGE` glue producing the same `(topic, topic_type, keys)` shape the tree builder consumes.
- `backend/tests/test_signal_tree.py`, `backend/tests/test_live_topics.py`.

**Backend — modified:**
- `backend/app/routers/signals.py` — `/signals/catalog` replaced by `/signals/tree/historical` and `/signals/tree/live`; `/signals/descriptive` unchanged.
- `backend/tests/test_signals_router.py` — updated for the new endpoint/shape.
- `bridge/app/filter.py`, `bridge/app/main.py`, `bridge/tests/test_filter.py` — `is_informative_topic` → `is_bridgeable_topic`, also matching `_analytical`.

**Frontend — new:**
- `frontend/src/lib/palette.ts` (+ `__tests__/palette.test.ts`) — `resolveColor`, `DEFAULT_PALETTE`.
- `frontend/src/lib/connectionState.ts` (+ `__tests__/connectionState.test.ts`) — `computeConnectionState`, `ConnectionState`.
- `frontend/src/components/editor/SignalTreePicker.tsx` (+ `__tests__/SignalTreePicker.test.tsx`) — replaces `SignalPicker.tsx`.
- `frontend/src/hooks/__tests__/useHistoricalQuery.test.ts`.
- `frontend/src/components/charts/__tests__/BarChart.test.tsx`.

**Frontend — modified:**
- `frontend/src/types/dashboard.ts` — add `SignalTreeNode`/`SignalTreeLeaf`.
- `frontend/src/api/client.ts` — `signals.catalog` → `signals.treeHistorical`/`signals.treeLive`.
- `frontend/src/hooks/useDashboardSocket.ts` — expose `wsOpen`/`lastFrameAt`/`connectedAt`.
- `frontend/src/hooks/useHistoricalQuery.ts` — return `{points, error, retry}`.
- `frontend/src/components/ChartCardShell.tsx` — connection-state-aware badge, `onEdit` button.
- `frontend/src/components/ChartRenderer.tsx` — color injection, connection-state wiring, historical error/retry UI, `onEdit` passthrough.
- `frontend/src/components/charts/{TimeSeriesChart,GaugeChart,BarChart}.tsx` — ECharts rewrite.
- `frontend/src/components/charts/{KpiTile,StatusIndicator}.tsx` — consume a resolved hex color instead of a hardcoded default / semantic enum.
- `frontend/src/components/editor/ChartForm.tsx` — `initial`/`onCancel` props (edit mode), uses `SignalTreePicker`.
- `frontend/src/pages/EditorPage.tsx` — `editingChart` state wiring.
- `frontend/package.json` — `+echarts +echarts-for-react`, `-recharts`.
- `frontend/src/test-setup.ts` — comment update (polyfill now also serves `echarts-for-react`).
- Delete: `frontend/src/components/editor/SignalPicker.tsx`.

---

### Task 1: Bridge forwards `_analytical` topics alongside `_informative`

**Files:**
- Modify: `bridge/app/filter.py`
- Modify: `bridge/app/main.py`
- Modify: `bridge/tests/test_filter.py`

**Interfaces:**
- Produces: `is_bridgeable_topic(topic: str) -> bool`, used by `bridge/app/main.py`'s `on_message`.

- [ ] **Step 1: Write the failing tests**

```python
# bridge/tests/test_filter.py
from app.filter import is_bridgeable_topic


def test_informative_suffix_matches():
    assert is_bridgeable_topic("Enterprise/Site/Area/_informative") is True


def test_analytical_suffix_matches():
    assert is_bridgeable_topic("Enterprise/Site/Area/_analytical") is True


def test_descriptive_suffix_does_not_match():
    assert is_bridgeable_topic("Enterprise/Site/Area/_descriptive") is False


def test_topic_without_suffix_does_not_match():
    assert is_bridgeable_topic("Enterprise/Site/Area") is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd bridge && python -m pytest tests/test_filter.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_bridgeable_topic'`

- [ ] **Step 3: Implement**

```python
# bridge/app/filter.py
_BRIDGEABLE_SUFFIXES = {"_informative", "_analytical"}


def is_bridgeable_topic(topic: str) -> bool:
    return topic.rsplit("/", 1)[-1] in _BRIDGEABLE_SUFFIXES
```

In `bridge/app/main.py`:
- Change the module docstring's second line from `` `_informative` topics, and XADDs `` to `` `_informative`/`_analytical` topics, and XADDs ``.
- Change `from app.filter import is_informative_topic` to `from app.filter import is_bridgeable_topic`.
- Change `if not is_informative_topic(message.topic):` to `if not is_bridgeable_topic(message.topic):`.

- [ ] **Step 4: Run it to verify it passes**

Run: `cd bridge && python -m pytest tests/test_filter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bridge/app/filter.py bridge/app/main.py bridge/tests/test_filter.py
git commit -m "feat(uns-dashboard): bridge forwards _analytical topics alongside _informative

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 2: Pure signal-tree builder service

**Files:**
- Create: `backend/app/services/signal_tree.py`
- Create: `backend/tests/test_signal_tree.py`

**Interfaces:**
- Produces: `topic_type_of(topic: str) -> str | None` (returns `"informative"`, `"analytical"`, or `None`); `build_tree(entries: list[tuple[str, str, list[str]]]) -> list[dict]` where each input tuple is `(topic, topic_type, keys)`.
- Consumed by: Task 3 (`/signals/tree/historical`) and Task 4 (`/signals/tree/live`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_signal_tree.py
from app.services.signal_tree import build_tree, topic_type_of


def test_topic_type_of_matches_informative_and_analytical():
    assert topic_type_of("a/b/_informative") == "informative"
    assert topic_type_of("a/b/_analytical") == "analytical"


def test_topic_type_of_returns_none_for_descriptive_and_unsuffixed():
    assert topic_type_of("a/b/_descriptive") is None
    assert topic_type_of("a/b") is None


def test_build_tree_nests_by_path_segment():
    tree = build_tree([("Planta1/Linea3/_informative", "informative", ["Gen_RPM_Avg"])])
    assert tree == [{
        "segment": "Planta1",
        "children": [{
            "segment": "Linea3",
            "children": [{
                "segment": "_informative",
                "children": [],
                "leaf": {"topic": "Planta1/Linea3/_informative", "topic_type": "informative", "keys": ["Gen_RPM_Avg"]},
            }],
        }],
    }]


def test_build_tree_merges_shared_prefixes_and_sorts_children():
    tree = build_tree([
        ("Planta1/L2/_informative", "informative", ["B"]),
        ("Planta1/L1/_informative", "informative", ["A"]),
    ])
    assert len(tree) == 1
    assert tree[0]["segment"] == "Planta1"
    assert [c["segment"] for c in tree[0]["children"]] == ["L1", "L2"]


def test_build_tree_empty_input_returns_empty_list():
    assert build_tree([]) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_signal_tree.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.signal_tree'`

- [ ] **Step 3: Implement**

```python
# backend/app/services/signal_tree.py
"""Pure topic-path -> nested-tree builder shared by the historical
(Historian-backed) and live (Redis-backed) signal-tree endpoints. Has no
I/O and is fully unit tested; see design spec Section 1."""
from __future__ import annotations

_BRIDGEABLE_SUFFIXES = {"_informative": "informative", "_analytical": "analytical"}

TopicEntry = tuple[str, str, list[str]]


def topic_type_of(topic: str) -> str | None:
    return _BRIDGEABLE_SUFFIXES.get(topic.rsplit("/", 1)[-1])


def build_tree(entries: list[TopicEntry]) -> list[dict]:
    root: dict = {"children": {}}

    for topic, topic_type, keys in entries:
        node = root
        for segment in topic.split("/"):
            node = node["children"].setdefault(segment, {"children": {}})
        node["leaf"] = {"topic": topic, "topic_type": topic_type, "keys": keys}

    def to_list(node: dict) -> list[dict]:
        result = []
        for segment, child in sorted(node["children"].items()):
            entry: dict = {"segment": segment, "children": to_list(child)}
            if "leaf" in child:
                entry["leaf"] = child["leaf"]
            result.append(entry)
        return result

    return to_list(root)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd backend && python -m pytest tests/test_signal_tree.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/signal_tree.py backend/tests/test_signal_tree.py
git commit -m "feat(uns-dashboard): pure signal-tree builder for hierarchical signal picker

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 3: Live signal discovery from Redis (`discover_live_topics`)

**Files:**
- Create: `backend/app/services/live_topics.py`
- Create: `backend/tests/test_live_topics.py`

**Interfaces:**
- Consumes: `topic_type_of` from Task 2.
- Produces: `discover_live_topics(redis_client) -> list[tuple[str, str, list[str]]]`, consumed by Task 4's `/signals/tree/live` route.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_live_topics.py
"""discover_live_topics only needs an object exposing async `scan_iter`
and `xrevrange` (the subset of redis.asyncio.Redis it calls), so it's
exercised here against a minimal in-memory fake instead of a live Redis
-- no live service needed for this logic."""
import json

import pytest

from app.services.live_topics import discover_live_topics


class FakeRedis:
    def __init__(self, streams: dict[str, list[tuple[str, dict]]]):
        self._streams = streams

    async def scan_iter(self, match: str, count: int = 100):
        for key in self._streams:
            yield key

    async def xrevrange(self, key: str, count: int = 1):
        return self._streams.get(key, [])[-count:][::-1]


@pytest.mark.asyncio
async def test_discover_live_topics_extracts_keys_from_latest_entry():
    fake = FakeRedis({
        "live:a/_informative": [("1-0", {"payload": json.dumps({"timestamp": "t", "Gen_RPM_Avg": 1300})})],
    })
    assert await discover_live_topics(fake) == [("a/_informative", "informative", ["Gen_RPM_Avg"])]


@pytest.mark.asyncio
async def test_discover_live_topics_skips_non_bridgeable_streams():
    fake = FakeRedis({"live:a/_descriptive": [("1-0", {"payload": "{}"})]})
    assert await discover_live_topics(fake) == []


@pytest.mark.asyncio
async def test_discover_live_topics_defaults_to_empty_keys_when_stream_is_empty():
    fake = FakeRedis({"live:a/_analytical": []})
    assert await discover_live_topics(fake) == [("a/_analytical", "analytical", [])]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_live_topics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.live_topics'`

- [ ] **Step 3: Implement**

```python
# backend/app/services/live_topics.py
"""Redis SCAN/XREVRANGE glue that discovers which topics the bridge is
currently mirroring into `live:<topic>` streams, for the live-mode
signal tree. Thin async I/O -- verified manually/live (see design spec
Section 1); the filtering/parsing logic is exercised here against a fake
Redis double, not a live one."""
from __future__ import annotations

import json

from app.services.signal_tree import topic_type_of

STREAM_PREFIX = "live:"


async def discover_live_topics(redis_client) -> list[tuple[str, str, list[str]]]:
    entries: list[tuple[str, str, list[str]]] = []
    async for key in redis_client.scan_iter(match=f"{STREAM_PREFIX}*", count=100):
        topic = key[len(STREAM_PREFIX):]
        topic_type = topic_type_of(topic)
        if topic_type is None:
            continue
        keys: list[str] = []
        latest = await redis_client.xrevrange(key, count=1)
        if latest:
            _entry_id, fields = latest[0]
            payload = json.loads(fields.get("payload", "{}"))
            if isinstance(payload, dict):
                keys = [k for k in payload.keys() if k != "timestamp"]
        entries.append((topic, topic_type, keys))
    return entries
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd backend && python -m pytest tests/test_live_topics.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/live_topics.py backend/tests/test_live_topics.py
git commit -m "feat(uns-dashboard): discover live signal topics from Redis for the live signal tree

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 4: `/signals/tree/historical` and `/signals/tree/live` replace `/signals/catalog`

**Files:**
- Modify: `backend/app/routers/signals.py`
- Modify: `backend/tests/test_signals_router.py`

**Interfaces:**
- Consumes: `topic_type_of`, `build_tree` from Task 2; `discover_live_topics` from Task 3.
- Produces: `GET /signals/tree/historical?topic_prefix=` and `GET /signals/tree/live`, both returning the shape from Task 2's `build_tree`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_signals_router.py
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


def _find_leaf(nodes: list[dict], topic: str) -> dict | None:
    for node in nodes:
        if node.get("leaf", {}).get("topic") == topic:
            return node["leaf"]
        found = _find_leaf(node["children"], topic)
        if found:
            return found
    return None


def test_tree_historical_nests_topics_and_lists_keys_for_both_suffixes(client: TestClient):
    from sqlalchemy import create_engine, text

    engine = create_engine(HISTORIAN_DATABASE_URL.replace("+asyncpg", "+psycopg"))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_tree/%'"))
        conn.execute(
            text(
                "INSERT INTO mqtt_messages (time, topic, payload, qos, retain) VALUES "
                "(now(), 'pytest_tree/gen/_informative', '{\"Gen_RPM_Avg\": 1300}', 1, false), "
                "(now(), 'pytest_tree/gen/_analytical', '{\"Health_Score\": 0.92}', 1, false)"
            )
        )

    response = client.get("/signals/tree/historical", params={"topic_prefix": "pytest_tree"})
    assert response.status_code == 200
    tree = response.json()

    informative_leaf = _find_leaf(tree, "pytest_tree/gen/_informative")
    assert informative_leaf["topic_type"] == "informative"
    assert "Gen_RPM_Avg" in informative_leaf["keys"]

    analytical_leaf = _find_leaf(tree, "pytest_tree/gen/_analytical")
    assert analytical_leaf["topic_type"] == "analytical"
    assert "Health_Score" in analytical_leaf["keys"]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_tree/%'"))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && HISTORIAN_DATABASE_URL=<your test historian URL> python -m pytest tests/test_signals_router.py -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Implement**

```python
# backend/app/routers/signals.py
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_historian_db
from app.services.descriptive_lookup import get_descriptive_signal_meta
from app.services.live_topics import discover_live_topics
from app.services.signal_tree import build_tree, topic_type_of

router = APIRouter(prefix="/signals", tags=["signals"])

_SUFFIX_CLAUSE = "(topic LIKE '%\\_informative' ESCAPE '\\' OR topic LIKE '%\\_analytical' ESCAPE '\\')"


@router.get("/tree/historical")
async def signal_tree_historical(
    topic_prefix: str = Query(""),
    historian_db: AsyncSession = Depends(get_historian_db),
):
    if topic_prefix:
        escaped_prefix = topic_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where_sql = f"topic LIKE :prefix ESCAPE '\\' AND {_SUFFIX_CLAUSE}"
        params = {"prefix": f"{escaped_prefix}%"}
    else:
        where_sql = _SUFFIX_CLAUSE
        params = {}

    topics_result = await historian_db.execute(
        text(f"SELECT DISTINCT topic FROM mqtt_messages WHERE {where_sql} ORDER BY topic"),
        params,
    )
    topics = [row[0] for row in topics_result.fetchall()]

    entries = []
    for topic in topics:
        latest = await historian_db.execute(
            text("SELECT payload FROM mqtt_messages WHERE topic = :topic ORDER BY time DESC LIMIT 1"),
            {"topic": topic},
        )
        row = latest.first()
        payload = row[0] if row else None
        keys = [k for k in payload.keys() if k != "timestamp"] if isinstance(payload, dict) else []
        topic_type = topic_type_of(topic)
        if topic_type:
            entries.append((topic, topic_type, keys))
    return build_tree(entries)


@router.get("/tree/live")
async def signal_tree_live():
    redis_client = aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    try:
        entries = await discover_live_topics(redis_client)
        return build_tree(entries)
    finally:
        await redis_client.aclose()


@router.get("/descriptive")
async def signal_descriptive(
    topic_prefix: str = Query(..., min_length=1),
    signal_key: str = Query(..., min_length=1),
):
    meta = await get_descriptive_signal_meta(topic_prefix, signal_key)
    return meta or {}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd backend && HISTORIAN_DATABASE_URL=<your test historian URL> python -m pytest tests/test_signals_router.py -v`
Expected: 1 passed. (The `/signals/tree/live` route added in the same step has no automated route-level test — it's thin I/O glue over `discover_live_topics`, which already has full unit coverage from Task 3; the route itself is verified manually in Task 15 against a running Redis.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/signals.py backend/tests/test_signals_router.py
git commit -m "feat(uns-dashboard): replace flat signal catalog with historical and live tree endpoints

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 5: Color resolution (`resolveColor`)

**Files:**
- Create: `frontend/src/lib/palette.ts`
- Create: `frontend/src/lib/__tests__/palette.test.ts`

**Interfaces:**
- Produces: `DEFAULT_PALETTE: string[]`, `resolveColor(signal: ChartSignal, chartColor: string | null | undefined, index: number, total: number): string`.
- Consumed by: Task 8 (`ChartForm`/`SignalTreePicker` swatches) and Task 12 (`ChartRenderer`).

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/lib/__tests__/palette.test.ts
import { describe, expect, it } from "vitest";
import { DEFAULT_PALETTE, resolveColor } from "../palette";
import type { ChartSignal } from "../../types/dashboard";

const signal = (color?: string | null): ChartSignal => ({ topic: "a", signal_key: "k", color: color ?? null });

describe("resolveColor", () => {
  it("prefers an explicit signal color override", () => {
    expect(resolveColor(signal("#FF0000"), "#000000", 0, 2)).toBe("#FF0000");
  });

  it("falls back to the chart color when there is exactly one signal", () => {
    expect(resolveColor(signal(), "#123456", 0, 1)).toBe("#123456");
  });

  it("falls back to the rotating palette by index for multi-signal charts", () => {
    expect(resolveColor(signal(), "#123456", 1, 3)).toBe(DEFAULT_PALETTE[1]);
  });

  it("wraps the palette index when there are more signals than colors", () => {
    const i = DEFAULT_PALETTE.length;
    expect(resolveColor(signal(), null, i, 10)).toBe(DEFAULT_PALETTE[0]);
  });

  it("uses the palette when there is one signal but no chart color set", () => {
    expect(resolveColor(signal(), null, 0, 1)).toBe(DEFAULT_PALETTE[0]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/lib/__tests__/palette.test.ts`
Expected: FAIL with a module-not-found error for `../palette`

- [ ] **Step 3: Implement**

```typescript
// frontend/src/lib/palette.ts
import type { ChartSignal } from "../types/dashboard";

export const DEFAULT_PALETTE = [
  "#198ACB", "#17865D", "#A9630B", "#C43F3F",
  "#6D5BD0", "#0E9F9F", "#B0538B", "#5E6872",
];

export function resolveColor(
  signal: ChartSignal,
  chartColor: string | null | undefined,
  index: number,
  total: number
): string {
  if (signal.color) return signal.color;
  if (total === 1 && chartColor) return chartColor;
  return DEFAULT_PALETTE[index % DEFAULT_PALETTE.length];
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run src/lib/__tests__/palette.test.ts`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/palette.ts frontend/src/lib/__tests__/palette.test.ts
git commit -m "feat(uns-dashboard): resolveColor unifies chart-color and per-signal-palette resolution

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 6: Connection-state computation (`computeConnectionState`)

**Files:**
- Create: `frontend/src/lib/connectionState.ts`
- Create: `frontend/src/lib/__tests__/connectionState.test.ts`

**Interfaces:**
- Produces: `type ConnectionState = "live" | "stale" | "reconnecting"`, `computeConnectionState(wsOpen: boolean, topics: string[], lastFrameAt: Record<string, number>, connectedAt: number, now: number, staleAfterMs?: number): ConnectionState`.
- Consumed by: Task 9 (`ChartCardShell`'s prop type) and Task 12 (`ChartRenderer`).

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/lib/__tests__/connectionState.test.ts
import { describe, expect, it } from "vitest";
import { computeConnectionState } from "../connectionState";

describe("computeConnectionState", () => {
  it("is reconnecting when the socket is not open", () => {
    expect(computeConnectionState(false, ["t"], {}, 0, 1000)).toBe("reconnecting");
  });

  it("is live right after connecting, before any frame has arrived", () => {
    expect(computeConnectionState(true, ["t"], {}, 1000, 1005)).toBe("live");
  });

  it("is live when a frame arrived recently", () => {
    expect(computeConnectionState(true, ["t"], { t: 1000 }, 0, 1005)).toBe("live");
  });

  it("is stale once the freshest frame is older than the threshold", () => {
    expect(computeConnectionState(true, ["t"], { t: 1000 }, 0, 1000 + 15_001)).toBe("stale");
  });

  it("is live with no configured topics -- nothing to be stale about", () => {
    expect(computeConnectionState(true, [], {}, 0, 999_999)).toBe("live");
  });

  it("takes the freshest of multiple topics", () => {
    expect(computeConnectionState(true, ["a", "b"], { a: 1000, b: 16_000 }, 0, 16_001)).toBe("live");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/lib/__tests__/connectionState.test.ts`
Expected: FAIL with a module-not-found error for `../connectionState`

- [ ] **Step 3: Implement**

```typescript
// frontend/src/lib/connectionState.ts
export type ConnectionState = "live" | "stale" | "reconnecting";

const STALE_AFTER_MS = 15_000;

export function computeConnectionState(
  wsOpen: boolean,
  topics: string[],
  lastFrameAt: Record<string, number>,
  connectedAt: number,
  now: number,
  staleAfterMs: number = STALE_AFTER_MS
): ConnectionState {
  if (!wsOpen) return "reconnecting";
  if (topics.length === 0) return "live";
  const freshest = Math.max(connectedAt, ...topics.map((t) => lastFrameAt[t] ?? 0));
  return now - freshest > staleAfterMs ? "stale" : "live";
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run src/lib/__tests__/connectionState.test.ts`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/connectionState.ts frontend/src/lib/__tests__/connectionState.test.ts
git commit -m "feat(uns-dashboard): computeConnectionState detects stale/reconnecting live charts

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 7: `SignalTreeNode` types and `api.signals` tree methods

**Files:**
- Modify: `frontend/src/types/dashboard.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces: `SignalTreeLeaf`, `SignalTreeNode` types; `api.signals.treeHistorical(topicPrefix?: string)`, `api.signals.treeLive()`.
- Consumed by: Task 8 (`SignalTreePicker`).

- [ ] **Step 1: Add the types**

In `frontend/src/types/dashboard.ts`, add after `ChartSignal`:

```typescript
export interface SignalTreeLeaf {
  topic: string;
  topic_type: "informative" | "analytical";
  keys: string[];
}

export interface SignalTreeNode {
  segment: string;
  children: SignalTreeNode[];
  leaf?: SignalTreeLeaf;
}
```

- [ ] **Step 2: Replace the `catalog` client method**

In `frontend/src/api/client.ts`, replace:

```typescript
    catalog: (topicPrefix: string) =>
      http.get<{ topic: string; keys: string[] }[]>("/signals/catalog", { params: { topic_prefix: topicPrefix } }).then((r) => r.data),
```

with:

```typescript
    treeHistorical: (topicPrefix = "") =>
      http.get<SignalTreeNode[]>("/signals/tree/historical", { params: { topic_prefix: topicPrefix } }).then((r) => r.data),
    treeLive: () =>
      http.get<SignalTreeNode[]>("/signals/tree/live").then((r) => r.data),
```

And add `SignalTreeNode` to the existing type-only import at the top of the file (`import type { Chart, Dashboard, DashboardDetail, HistoryPoint, SignalTreeNode } from "../types/dashboard";`).

- [ ] **Step 3: Verify the project still typechecks**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only in `ChartForm.tsx`/`SignalPicker.tsx` for the now-removed `api.signals.catalog` — expected until Task 8 replaces those call sites; no other file should reference `api.signals.catalog`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/dashboard.ts frontend/src/api/client.ts
git commit -m "feat(uns-dashboard): add signal-tree types and API client methods

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 8: `SignalTreePicker` replaces `SignalPicker`

**Files:**
- Create: `frontend/src/components/editor/SignalTreePicker.tsx`
- Create: `frontend/src/components/editor/__tests__/SignalTreePicker.test.tsx`
- Delete: `frontend/src/components/editor/SignalPicker.tsx`

**Interfaces:**
- Consumes: `api.signals.treeHistorical`/`treeLive`/`descriptive` (Task 7), `resolveColor` (Task 5), `SignalTreeNode` (Task 7).
- Produces: `SignalTreePicker({ source: "historical" | "live"; selected: ChartSignal[]; chartColor: string | null; onChange: (signals: ChartSignal[]) => void })`, consumed by Task 10 (`ChartForm`).

- [ ] **Step 1: Write the failing tests**

```typescript jsx
// frontend/src/components/editor/__tests__/SignalTreePicker.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SignalTreePicker } from "../SignalTreePicker";
import { api } from "../../../api/client";

vi.mock("../../../api/client", () => ({
  api: {
    signals: {
      treeHistorical: vi.fn(),
      treeLive: vi.fn(),
      descriptive: vi.fn(),
    },
  },
}));

const tree = [{
  segment: "Planta1",
  children: [{
    segment: "_informative",
    children: [],
    leaf: { topic: "Planta1/_informative", topic_type: "informative" as const, keys: ["Gen_RPM_Avg"] },
  }],
}];

describe("SignalTreePicker", () => {
  it("lists a leaf's keys as addable buttons once the historical tree loads", async () => {
    (api.signals.treeHistorical as any).mockResolvedValue(tree);
    render(<SignalTreePicker source="historical" selected={[]} chartColor={null} onChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("+ Gen_RPM_Avg")).toBeInTheDocument());
  });

  it("calls the live tree endpoint when source is live", async () => {
    (api.signals.treeLive as any).mockResolvedValue([]);
    render(<SignalTreePicker source="live" selected={[]} chartColor={null} onChange={() => {}} />);
    await waitFor(() => expect(api.signals.treeLive).toHaveBeenCalled());
    expect(api.signals.treeHistorical).not.toHaveBeenCalled();
  });

  it("adds a signal with descriptive metadata prefill, stripping the _informative suffix", async () => {
    (api.signals.treeHistorical as any).mockResolvedValue(tree);
    (api.signals.descriptive as any).mockResolvedValue({ unit: "rpm" });
    const onChange = vi.fn();
    render(<SignalTreePicker source="historical" selected={[]} chartColor={null} onChange={onChange} />);
    fireEvent.click(await screen.findByText("+ Gen_RPM_Avg"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ topic: "Planta1/_informative", signal_key: "Gen_RPM_Avg", unit: "rpm", source: "auto" }),
    ]));
    expect(api.signals.descriptive).toHaveBeenCalledWith("Planta1", "Gen_RPM_Avg");
  });

  it("shows an inline error when the tree fetch fails", async () => {
    (api.signals.treeHistorical as any).mockRejectedValue(new Error("network"));
    render(<SignalTreePicker source="historical" selected={[]} chartColor={null} onChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("No se pudo cargar el árbol histórico.")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/editor/__tests__/SignalTreePicker.test.tsx`
Expected: FAIL with a module-not-found error for `../SignalTreePicker`

- [ ] **Step 3: Implement**

```typescript jsx
// frontend/src/components/editor/SignalTreePicker.tsx
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { resolveColor } from "../../lib/palette";
import type { ChartSignal, SignalTreeNode } from "../../types/dashboard";

function matchesFilter(node: SignalTreeNode, filter: string): boolean {
  if (!filter) return true;
  const needle = filter.toLowerCase();
  if (node.segment.toLowerCase().includes(needle)) return true;
  if (node.leaf?.keys.some((k) => k.toLowerCase().includes(needle))) return true;
  return node.children.some((c) => matchesFilter(c, filter));
}

function TreeBranch({
  node,
  filter,
  onAdd,
}: {
  node: SignalTreeNode;
  filter: string;
  onAdd: (topic: string, signalKey: string) => void;
}) {
  const [open, setOpen] = useState(!!filter);
  if (!matchesFilter(node, filter)) return null;

  if (node.leaf) {
    const needle = filter.toLowerCase();
    const keys = node.leaf.keys.filter(
      (k) => !filter || k.toLowerCase().includes(needle) || node.segment.toLowerCase().includes(needle)
    );
    return (
      <div className="pl-2">
        <div className="flex items-center gap-1.5 text-xs text-ink-muted">
          <span className="border border-border rounded px-1 text-[10px] uppercase">{node.leaf.topic_type}</span>
          {node.segment}
        </div>
        <div className="flex flex-wrap gap-1 pl-2 py-1">
          {keys.map((key) => (
            <button
              key={key}
              onClick={() => onAdd(node.leaf!.topic, key)}
              className="border border-border rounded px-2 py-0.5 text-xs"
            >
              + {key}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="pl-2">
      <button onClick={() => setOpen(!open)} className="text-xs font-semibold text-ink-secondary">
        {open ? "▾" : "▸"} {node.segment}
      </button>
      {open && node.children.map((child) => (
        <TreeBranch key={child.segment} node={child} filter={filter} onAdd={onAdd} />
      ))}
    </div>
  );
}

export function SignalTreePicker({
  source,
  selected,
  chartColor,
  onChange,
}: {
  source: "historical" | "live";
  selected: ChartSignal[];
  chartColor: string | null;
  onChange: (signals: ChartSignal[]) => void;
}) {
  const [tree, setTree] = useState<SignalTreeNode[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    const fetchTree = source === "historical" ? api.signals.treeHistorical() : api.signals.treeLive();
    fetchTree.then(setTree).catch(() =>
      setError(source === "historical" ? "No se pudo cargar el árbol histórico." : "No se pudo cargar el árbol en vivo.")
    );
  }, [source]);

  const addSignal = async (topic: string, signalKey: string) => {
    setError(null);
    try {
      const descriptivePrefix = topic.replace(/\/_(informative|analytical)$/, "");
      const descriptive = await api.signals.descriptive(descriptivePrefix, signalKey);
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
    } catch {
      setError("No se pudo añadir la señal.");
    }
  };

  const removeSignal = (topic: string, signalKey: string) => {
    onChange(selected.filter((s) => !(s.topic === topic && s.signal_key === signalKey)));
  };

  const setSignalColor = (topic: string, signalKey: string, color: string) => {
    onChange(selected.map((s) => (s.topic === topic && s.signal_key === signalKey ? { ...s, color } : s)));
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-bold text-ink-secondary">
        Señales ({source === "historical" ? "histórico" : "en vivo"})
      </label>
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filtrar por nombre…"
        className="border border-border rounded px-2 py-1 text-xs"
      />
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {selected.map((s, i) => (
          <span key={`${s.topic}|${s.signal_key}`} className="bg-surface-subtle rounded-full px-3 py-1 text-xs flex items-center gap-1.5">
            <input
              type="color"
              value={resolveColor(s, chartColor, i, selected.length)}
              onChange={(e) => setSignalColor(s.topic, s.signal_key, e.target.value)}
              className="w-4 h-4 border-0 p-0 bg-transparent"
            />
            {s.label}
            <button onClick={() => removeSignal(s.topic, s.signal_key)}>✕</button>
          </span>
        ))}
      </div>
      <div className="max-h-56 overflow-y-auto border border-border rounded-lg p-2">
        {tree.map((node) => (
          <TreeBranch key={node.segment} node={node} filter={filter} onAdd={addSignal} />
        ))}
      </div>
    </div>
  );
}
```

Delete `frontend/src/components/editor/SignalPicker.tsx` (no test file references it, and after Task 10 nothing imports it).

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run src/components/editor/__tests__/SignalTreePicker.test.tsx`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/editor/SignalTreePicker.tsx frontend/src/components/editor/__tests__/SignalTreePicker.test.tsx
git rm frontend/src/components/editor/SignalPicker.tsx
git commit -m "feat(uns-dashboard): hierarchical, dual-source signal tree picker replaces flat search

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 9: `ChartCardShell` — connection badge + edit button

**Files:**
- Modify: `frontend/src/components/ChartCardShell.tsx`

**Interfaces:**
- Consumes: `ConnectionState` type (Task 6).
- Produces: `ChartCardShell({ title, modeLabel, connectionState?, editable, onRemove?, onEdit?, children })`, consumed by Task 12 (`ChartRenderer`).

- [ ] **Step 1: Implement**

```typescript jsx
// frontend/src/components/ChartCardShell.tsx
import type { ReactNode } from "react";
import type { ConnectionState } from "../lib/connectionState";

export function ChartCardShell({
  title,
  modeLabel,
  connectionState,
  editable,
  onRemove,
  onEdit,
  children,
}: {
  title: string;
  modeLabel: string;
  connectionState?: ConnectionState | null;
  editable: boolean;
  onRemove?: () => void;
  onEdit?: () => void;
  children: ReactNode;
}) {
  const badge = connectionState === "reconnecting"
    ? { text: "Reconectando…", cls: "bg-danger-soft text-danger" }
    : connectionState === "stale"
      ? { text: "Sin datos recientes", cls: "bg-warning-soft text-warning" }
      : { text: modeLabel, cls: modeLabel.startsWith("Live") ? "bg-success-soft text-success" : "bg-accent-soft text-accent" };

  return (
    <div className="h-full w-full bg-surface border border-border rounded-lg p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-bold text-ink">{title}</span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${badge.cls}`}>
            {badge.text}
          </span>
        </div>
        {editable && (
          <div className="flex items-center gap-2">
            {onEdit && <button onClick={onEdit} className="text-ink-muted text-xs">✎</button>}
            {onRemove && <button onClick={onRemove} className="text-ink-muted text-xs">✕</button>}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}
```

This is a pure presentational change with no new test file — its behavior is exercised end-to-end by Task 15's live verification and indirectly by any test that renders `ChartRenderer`. Typecheck it directly:

- [ ] **Step 2: Verify it typechecks**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only where `ChartRenderer.tsx` still calls the old `ChartCardShell` shape (fixed in Task 12) — no errors inside `ChartCardShell.tsx` itself.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChartCardShell.tsx
git commit -m "feat(uns-dashboard): ChartCardShell shows connection state and an edit button

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 10: `useDashboardSocket` exposes connection state inputs

**Files:**
- Modify: `frontend/src/hooks/useDashboardSocket.ts`

**Interfaces:**
- Produces: `useDashboardSocket(dashboardId, topics) -> { frames: Record<string, LiveFrame>; wsOpen: boolean; lastFrameAt: Record<string, number>; connectedAt: number }` (was `Record<string, LiveFrame>`).
- Consumed by: Task 12 (`ChartRenderer`).

- [ ] **Step 1: Implement**

```typescript
// frontend/src/hooks/useDashboardSocket.ts
import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api/client";

export interface LiveFrame {
  time: string;
  payload: Record<string, number>;
}

export interface DashboardSocketState {
  frames: Record<string, LiveFrame>;
  wsOpen: boolean;
  lastFrameAt: Record<string, number>;
  connectedAt: number;
}

export function useDashboardSocket(dashboardId: string, topics: string[]): DashboardSocketState {
  const [frames, setFrames] = useState<Record<string, LiveFrame>>({});
  const [wsOpen, setWsOpen] = useState(false);
  const [lastFrameAt, setLastFrameAt] = useState<Record<string, number>>({});
  const [connectedAt, setConnectedAt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (topics.length === 0) return;
    stoppedRef.current = false;

    const connect = () => {
      const socket = new WebSocket(wsUrl(dashboardId));
      socketRef.current = socket;
      socket.onopen = () => {
        setWsOpen(true);
        setConnectedAt(Date.now());
        socket.send(JSON.stringify({ subscribe: topics }));
      };
      socket.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          setFrames((prev) => ({ ...prev, [frame.topic]: { time: frame.time, payload: frame.payload } }));
          setLastFrameAt((prev) => ({ ...prev, [frame.topic]: Date.now() }));
        } catch {
          /* ignore malformed frame */
        }
      };
      socket.onclose = () => {
        setWsOpen(false);
        if (stoppedRef.current) return;
        reconnectTimeoutRef.current = setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      stoppedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
      }
    };
  }, [dashboardId, topics.join(",")]);

  return { frames, wsOpen, lastFrameAt, connectedAt };
}
```

No dedicated hook test (consistent with v1 — the WebSocket glue is thin I/O, verified live only; its testable logic was already extracted into `computeConnectionState`, Task 6).

- [ ] **Step 2: Verify it typechecks**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only in `ChartRenderer.tsx` (still destructuring the old bare-object return; fixed in Task 12)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useDashboardSocket.ts
git commit -m "feat(uns-dashboard): useDashboardSocket exposes wsOpen/lastFrameAt/connectedAt

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 11: `useHistoricalQuery` returns `{points, error, retry}`

**Files:**
- Modify: `frontend/src/hooks/useHistoricalQuery.ts`
- Create: `frontend/src/hooks/__tests__/useHistoricalQuery.test.ts`

**Interfaces:**
- Produces: `useHistoricalQuery(chartId, rangeType, relativeRule) -> { points: HistoryPoint[]; error: boolean; retry: () => void }` (was `HistoryPoint[]`).
- Consumed by: Task 12 (`ChartRenderer`).

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/hooks/__tests__/useHistoricalQuery.test.ts
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useHistoricalQuery } from "../useHistoricalQuery";
import { api } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: { history: { get: vi.fn() } },
}));

describe("useHistoricalQuery", () => {
  it("returns points on a successful fetch", async () => {
    (api.history.get as any).mockResolvedValue({ points: [{ time: "t", v: 1 }] });
    const { result } = renderHook(() => useHistoricalQuery("chart-1", "fixed", null));
    await waitFor(() => expect(result.current.points).toEqual([{ time: "t", v: 1 }]));
    expect(result.current.error).toBe(false);
  });

  it("sets error and keeps points empty on a failed fetch", async () => {
    (api.history.get as any).mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useHistoricalQuery("chart-1", "fixed", null));
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.points).toEqual([]);
  });

  it("retry re-fetches and clears the error once it succeeds", async () => {
    (api.history.get as any)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ points: [{ time: "t", v: 2 }] });
    const { result } = renderHook(() => useHistoricalQuery("chart-1", "fixed", null));
    await waitFor(() => expect(result.current.error).toBe(true));

    result.current.retry();

    await waitFor(() => expect(result.current.error).toBe(false));
    expect(result.current.points).toEqual([{ time: "t", v: 2 }]);
  });

  it("does not fetch when rangeType is null", () => {
    renderHook(() => useHistoricalQuery("chart-1", null, null));
    expect(api.history.get).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useHistoricalQuery.test.ts`
Expected: FAIL — `result.current.error` is `undefined`, not part of today's return shape

- [ ] **Step 3: Implement**

```typescript
// frontend/src/hooks/useHistoricalQuery.ts
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { pollIntervalMsFor } from "../lib/refreshInterval";
import type { HistoricalRangeType, HistoryPoint, RelativeRule } from "../types/dashboard";

export interface HistoricalQueryResult {
  points: HistoryPoint[];
  error: boolean;
  retry: () => void;
}

export function useHistoricalQuery(
  chartId: string,
  rangeType: HistoricalRangeType | null | undefined,
  relativeRule: RelativeRule | null | undefined
): HistoricalQueryResult {
  const [points, setPoints] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState(false);
  const [retryTick, setRetryTick] = useState(0);

  const retry = useCallback(() => setRetryTick((n) => n + 1), []);

  useEffect(() => {
    if (!rangeType) return;

    let cancelled = false;
    const fetchOnce = () => {
      api.history.get(chartId).then((res) => {
        if (cancelled) return;
        setPoints(res.points);
        setError(false);
      }).catch(() => {
        if (cancelled) return;
        setError(true);
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
  }, [chartId, rangeType, relativeRule, retryTick]);

  return { points, error, retry };
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useHistoricalQuery.test.ts`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useHistoricalQuery.ts frontend/src/hooks/__tests__/useHistoricalQuery.test.ts
git commit -m "feat(uns-dashboard): useHistoricalQuery surfaces fetch errors with manual retry

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 12: `ChartRenderer` wiring — colors, connection state, historical errors; `KpiTile`/`StatusIndicator` consume resolved colors

**Files:**
- Modify: `frontend/src/components/ChartRenderer.tsx`
- Modify: `frontend/src/components/charts/KpiTile.tsx`
- Modify: `frontend/src/components/charts/StatusIndicator.tsx`
- Create: `frontend/src/components/charts/__tests__/StatusIndicator.test.tsx`

**Interfaces:**
- Consumes: `resolveColor` (Task 5), `computeConnectionState` (Task 6), `ChartCardShell`'s new props (Task 9), `useDashboardSocket`'s new return shape (Task 10), `useHistoricalQuery`'s new return shape (Task 11).
- Produces: `ChartRenderer({ dashboardId, chart, editable, onRemove?, onEdit? })` (adds `onEdit`), consumed by Task 14 (`EditorPage`).

- [ ] **Step 1: Write the failing test for `StatusIndicator`**

```typescript jsx
// frontend/src/components/charts/__tests__/StatusIndicator.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusIndicator } from "../StatusIndicator";

describe("StatusIndicator", () => {
  it("renders each state's label/value with its resolved color", () => {
    render(<StatusIndicator states={[{ label: "Bomba 1", value: "ON", color: "#17865D" }]} />);
    const value = screen.getByText("ON");
    expect(value).toHaveStyle({ color: "#17865D" });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/charts/__tests__/StatusIndicator.test.tsx`
Expected: FAIL — current `StatusIndicator` requires `color: "success"|"warning"|"danger"`, rejecting `"#17865D"` at the type level and rendering via the `TEXT_CLASS` map instead of an inline style

- [ ] **Step 3: Implement**

```typescript jsx
// frontend/src/components/charts/StatusIndicator.tsx
export function StatusIndicator({ states }: { states: { label: string; value: string; color: string }[] }) {
  return (
    <div className="h-full flex flex-col justify-center gap-2">
      {states.map((s) => (
        <div key={s.label} className="flex items-center justify-between bg-surface-subtle rounded px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-ink">{s.label}</span>
          </div>
          <span className="text-xs font-bold" style={{ color: s.color }}>{s.value}</span>
        </div>
      ))}
    </div>
  );
}
```

```typescript jsx
// frontend/src/components/charts/KpiTile.tsx
import type { ChartSignal } from "../../types/dashboard";

export function KpiTile({ signal, value }: { signal: ChartSignal; value: number }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <span className="text-4xl font-extrabold" style={{ color: signal.color ?? "#171A1D" }}>{value}</span>
      <span className="text-xs text-ink-secondary">{signal.unit} · {signal.label ?? signal.signal_key}</span>
    </div>
  );
}
```

```typescript jsx
// frontend/src/components/ChartRenderer.tsx
import { useEffect, useRef, useState } from "react";
import { ChartCardShell } from "./ChartCardShell";
import { TimeSeriesChart } from "./charts/TimeSeriesChart";
import { BarChart } from "./charts/BarChart";
import { GaugeChart } from "./charts/GaugeChart";
import { KpiTile } from "./charts/KpiTile";
import { StatusIndicator } from "./charts/StatusIndicator";
import { ValuesTable } from "./charts/ValuesTable";
import { useDashboardSocket } from "../hooks/useDashboardSocket";
import { useHistoricalQuery } from "../hooks/useHistoricalQuery";
import { resolveColor } from "../lib/palette";
import { computeConnectionState } from "../lib/connectionState";
import type { Chart, HistoryPoint } from "../types/dashboard";

const LIVE_BUFFER_MAX_POINTS = 200;

export function ChartRenderer({
  dashboardId,
  chart,
  editable,
  onRemove,
  onEdit,
}: {
  dashboardId: string;
  chart: Chart;
  editable: boolean;
  onRemove?: () => void;
  onEdit?: () => void;
}) {
  const topics = chart.data_mode === "live" ? [...new Set(chart.signals.map((s) => s.topic))] : [];
  const { frames: liveFrames, wsOpen, lastFrameAt, connectedAt } = useDashboardSocket(dashboardId, topics);
  const { points: historyPoints, error: historyError, retry: retryHistory } = useHistoricalQuery(
    chart.id,
    chart.data_mode === "historical" ? chart.historical_range_type : null,
    chart.data_mode === "historical" ? chart.historical_relative_rule : null
  );

  const signals = chart.signals.map((s, i) => ({ ...s, color: resolveColor(s, chart.color, i, chart.signals.length) }));

  const [, forceTick] = useState(0);
  useEffect(() => {
    if (chart.data_mode !== "live") return;
    const id = setInterval(() => forceTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, [chart.data_mode]);

  const connectionState = chart.data_mode === "live"
    ? computeConnectionState(wsOpen, topics, lastFrameAt, connectedAt, Date.now())
    : null;

  const [liveBuffer, setLiveBuffer] = useState<HistoryPoint[]>([]);
  const lastFrameKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (chart.data_mode !== "live" || chart.chart_type !== "timeseries") return;
    const frameKey = Object.values(liveFrames).map((f) => f.time).join(",");
    if (!frameKey || frameKey === lastFrameKeyRef.current) return;
    lastFrameKeyRef.current = frameKey;
    const point: HistoryPoint = { time: new Date().toISOString() };
    for (const s of signals) {
      const v = liveFrames[s.topic]?.payload[s.signal_key];
      if (v !== undefined) point[s.signal_key] = v;
    }
    setLiveBuffer((prev) => [...prev, point].slice(-LIVE_BUFFER_MAX_POINTS));
  }, [liveFrames, chart.data_mode, chart.chart_type, signals]);

  const liveValue = (signalKey: string, topic: string): number | null => {
    const v = liveFrames[topic]?.payload[signalKey];
    return typeof v === "number" ? v : null;
  };

  const lastHistoricalValue = (signalKey: string): number | null => {
    for (let i = historyPoints.length - 1; i >= 0; i--) {
      const v = historyPoints[i][signalKey];
      if (typeof v === "number") return v;
    }
    return null;
  };

  const currentValue = (signalKey: string, topic: string): number | null =>
    chart.data_mode === "live" ? liveValue(signalKey, topic) : lastHistoricalValue(signalKey);

  const modeLabel = chart.data_mode === "live"
    ? "Live · tiempo real"
    : chart.historical_range_type === "relative"
      ? `Histórico · ${chart.historical_relative_rule}`
      : "Histórico · rango fijo";

  const body = () => {
    if (chart.data_mode === "historical" && historyError && historyPoints.length === 0) {
      return (
        <div className="h-full flex flex-col items-center justify-center gap-2 text-center">
          <p className="text-xs text-danger">No se pudo cargar el histórico.</p>
          <button onClick={retryHistory} className="text-xs font-semibold text-accent">Reintentar</button>
        </div>
      );
    }
    switch (chart.chart_type) {
      case "timeseries": {
        const points = chart.data_mode === "live" ? liveBuffer : historyPoints;
        return <TimeSeriesChart signals={signals} points={points} />;
      }
      case "bar": {
        const values = Object.fromEntries(signals.map((s) => [s.signal_key, currentValue(s.signal_key, s.topic) ?? 0]));
        return <BarChart signals={signals} values={values} />;
      }
      case "gauge": {
        const first = signals[0];
        return <GaugeChart signal={first} value={currentValue(first?.signal_key, first?.topic) ?? 0} />;
      }
      case "kpi": {
        const first = signals[0];
        return <KpiTile signal={first} value={currentValue(first?.signal_key, first?.topic) ?? 0} />;
      }
      case "status":
        return (
          <StatusIndicator
            states={signals.map((s) => ({
              label: s.label ?? s.signal_key,
              value: String(currentValue(s.signal_key, s.topic) ?? "—"),
              color: s.color,
            }))}
          />
        );
      case "table": {
        const values = Object.fromEntries(
          signals.map((s) => [
            s.signal_key,
            {
              value: currentValue(s.signal_key, s.topic) ?? 0,
              updatedAt: chart.data_mode === "live"
                ? (liveFrames[s.topic]?.time ?? "—")
                : (historyPoints[historyPoints.length - 1]?.time ?? "—"),
            },
          ])
        );
        return <ValuesTable signals={signals} values={values} />;
      }
    }
  };

  return (
    <ChartCardShell title={chart.name} modeLabel={modeLabel} connectionState={connectionState} editable={editable} onRemove={onRemove} onEdit={onEdit}>
      {body()}
    </ChartCardShell>
  );
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run src/components/charts/__tests__/StatusIndicator.test.tsx && npx tsc --noEmit`
Expected: 1 passed; typecheck clean across the whole frontend (this task closes out every type mismatch left open by Tasks 9–11)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChartRenderer.tsx frontend/src/components/charts/KpiTile.tsx frontend/src/components/charts/StatusIndicator.tsx frontend/src/components/charts/__tests__/StatusIndicator.test.tsx
git commit -m "feat(uns-dashboard): wire resolved colors, connection state, and historical retry into ChartRenderer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 13: ECharts migration — `TimeSeriesChart` (with zoom), `GaugeChart`, `BarChart`

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/components/charts/TimeSeriesChart.tsx`
- Modify: `frontend/src/components/charts/GaugeChart.tsx`
- Modify: `frontend/src/components/charts/BarChart.tsx`
- Modify: `frontend/src/test-setup.ts`
- Create: `frontend/src/components/charts/__tests__/BarChart.test.tsx`

**Interfaces:**
- No prop-shape changes — `TimeSeriesChart`, `GaugeChart`, and `BarChart` keep the exact same props `ChartRenderer` (Task 12) already passes them.

- [ ] **Step 1: Install ECharts, remove recharts**

Run: `cd frontend && npm uninstall recharts && npm install echarts echarts-for-react`
Expected: `frontend/package.json`'s `dependencies` now has `echarts`/`echarts-for-react` instead of `recharts`.

- [ ] **Step 2: Write the failing test for `BarChart`** (no prior test existed for it)

```typescript jsx
// frontend/src/components/charts/__tests__/BarChart.test.tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarChart } from "../BarChart";

describe("BarChart", () => {
  it("renders an svg chart without crashing", () => {
    const { container } = render(
      <BarChart
        signals={[{ topic: "a", signal_key: "Gen_RPM_Avg", label: "RPM", color: "#198ACB" }]}
        values={{ Gen_RPM_Avg: 1300 }}
      />
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/charts/__tests__/BarChart.test.tsx`
Expected: FAIL — the current `BarChart` renders plain `div`s, no `<svg>`

- [ ] **Step 4: Implement the three chart components**

```typescript jsx
// frontend/src/components/charts/TimeSeriesChart.tsx
import ReactECharts from "echarts-for-react";
import type { ChartSignal, HistoryPoint } from "../../types/dashboard";

export function TimeSeriesChart({ signals, points }: { signals: ChartSignal[]; points: HistoryPoint[] }) {
  const times = points.map((p) => p.time);
  const option = {
    grid: { left: 40, right: 16, top: 16, bottom: 48 },
    xAxis: { type: "category", data: times, axisLabel: { show: false }, axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { fontSize: 10 } },
    tooltip: { trigger: "axis" },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 4 }],
    series: signals.map((s) => ({
      name: s.label ?? s.signal_key,
      type: "line",
      areaStyle: { opacity: 0.15 },
      showSymbol: false,
      smooth: true,
      lineStyle: { color: s.color ?? "#3B82F6" },
      itemStyle: { color: s.color ?? "#3B82F6" },
      data: points.map((p) => (p[s.signal_key] as number) ?? null),
    })),
  };

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
      <div className="flex-1 min-h-0">
        <ReactECharts option={option} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} notMerge />
      </div>
    </div>
  );
}
```

```typescript jsx
// frontend/src/components/charts/GaugeChart.tsx
import ReactECharts from "echarts-for-react";
import type { ChartSignal } from "../../types/dashboard";

export function GaugeChart({ signal, value }: { signal: ChartSignal; value: number }) {
  const min = signal.min ?? 0;
  const max = signal.max ?? 100;
  const color = signal.color ?? "#198ACB";

  const option = {
    series: [{
      type: "gauge",
      min,
      max,
      startAngle: 225,
      endAngle: -45,
      progress: { show: true, width: 10, itemStyle: { color } },
      axisLine: { lineStyle: { width: 10, color: [[1, "#DDE2E7"]] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      detail: { show: false },
      data: [{ value }],
    }],
  };

  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <div className="w-32 h-32">
        <ReactECharts option={option} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} notMerge />
      </div>
      <span className="text-2xl font-bold text-ink -mt-16">{value}{signal.unit}</span>
      <span className="text-xs text-ink-secondary mt-16">{signal.label ?? signal.signal_key}</span>
    </div>
  );
}
```

```typescript jsx
// frontend/src/components/charts/BarChart.tsx
import ReactECharts from "echarts-for-react";
import type { ChartSignal } from "../../types/dashboard";

export function BarChart({ signals, values }: { signals: ChartSignal[]; values: Record<string, number> }) {
  const option = {
    grid: { left: 40, right: 16, top: 24, bottom: 32 },
    xAxis: { type: "category", data: signals.map((s) => s.label ?? s.signal_key), axisLabel: { fontSize: 10 } },
    yAxis: { type: "value", axisLabel: { fontSize: 10 } },
    series: [{
      type: "bar",
      data: signals.map((s) => ({ value: values[s.signal_key] ?? 0, itemStyle: { color: s.color ?? "#3B82F6" } })),
      label: {
        show: true,
        position: "top",
        fontSize: 10,
        formatter: (p: { dataIndex: number; value: number }) => `${p.value}${signals[p.dataIndex]?.unit ?? ""}`,
      },
    }],
  };

  return <ReactECharts option={option} style={{ height: "100%", width: "100%" }} opts={{ renderer: "svg" }} notMerge />;
}
```

In `frontend/src/test-setup.ts`, update the comment (behavior unchanged):

```typescript
// frontend/src/test-setup.ts
import "@testing-library/jest-dom/vitest";

// Polyfill for ResizeObserver (needed by echarts-for-react's auto-resize)
(globalThis as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd frontend && npx vitest run`
Expected: all test files pass, including the unchanged `GaugeChart.test.tsx`/`TimeSeriesChart.test.tsx` (their DOM assertions target the label/legend spans, not chart internals, so they need no edits) and the new `BarChart.test.tsx`

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/charts/TimeSeriesChart.tsx frontend/src/components/charts/GaugeChart.tsx frontend/src/components/charts/BarChart.tsx frontend/src/components/charts/__tests__/BarChart.test.tsx frontend/src/test-setup.ts
git commit -m "feat(uns-dashboard): migrate timeseries/gauge/bar to ECharts, adding native zoom to timeseries

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 14: `ChartForm` edit mode; `EditorPage` wiring

**Files:**
- Modify: `frontend/src/components/editor/ChartForm.tsx`
- Modify: `frontend/src/pages/EditorPage.tsx`

**Interfaces:**
- Consumes: `SignalTreePicker` (Task 8).
- Produces: `ChartForm({ initial?: Chart; onSubmit: (chart: Omit<Chart, "id"|"dashboard_id">) => void; onCancel?: () => void })` (was `{ topicPrefix, onSubmit }`).

- [ ] **Step 1: Implement `ChartForm`**

```typescript jsx
// frontend/src/components/editor/ChartForm.tsx
import { useState } from "react";
import { SignalTreePicker } from "./SignalTreePicker";
import type { Chart, ChartSignal, ChartType, DataMode, HistoricalRangeType, RelativeRule } from "../../types/dashboard";

const CHART_TYPES: ChartType[] = ["timeseries", "gauge", "kpi", "bar", "table", "status"];
const RELATIVE_RULES: RelativeRule[] = ["1h", "24h", "7d", "30d"];

export function ChartForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: Chart;
  onSubmit: (chart: Omit<Chart, "id" | "dashboard_id">) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [chartType, setChartType] = useState<ChartType>(initial?.chart_type ?? "timeseries");
  const [signals, setSignals] = useState<ChartSignal[]>(initial?.signals ?? []);
  const [dataMode, setDataMode] = useState<DataMode>(initial?.data_mode ?? "live");
  const [rangeType, setRangeType] = useState<HistoricalRangeType>(initial?.historical_range_type ?? "relative");
  const [relativeRule, setRelativeRule] = useState<RelativeRule>(initial?.historical_relative_rule ?? "24h");
  const [historicalFrom, setHistoricalFrom] = useState(initial?.historical_from?.slice(0, 16) ?? "");
  const [historicalTo, setHistoricalTo] = useState(initial?.historical_to?.slice(0, 16) ?? "");
  const [color, setColor] = useState(initial?.color ?? "#198ACB");

  const submit = () => {
    onSubmit({
      name,
      chart_type: chartType,
      data_mode: dataMode,
      historical_range_type: dataMode === "historical" ? rangeType : null,
      historical_relative_rule: dataMode === "historical" && rangeType === "relative" ? relativeRule : null,
      historical_from: dataMode === "historical" && rangeType === "fixed" && historicalFrom ? new Date(historicalFrom).toISOString() : null,
      historical_to: dataMode === "historical" && rangeType === "fixed" && historicalTo ? new Date(historicalTo).toISOString() : null,
      layout_x: initial?.layout_x ?? 0,
      layout_y: initial?.layout_y ?? 0,
      layout_w: initial?.layout_w ?? 4,
      layout_h: initial?.layout_h ?? 4,
      color,
      config: initial?.config ?? null,
      signals,
    });
    if (!initial) {
      setName("");
      setSignals([]);
    }
  };

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-4">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-ink-muted uppercase">{initial ? "Editar gráfica" : "Nueva gráfica"}</label>
        {initial && onCancel && <button onClick={onCancel} className="text-xs text-ink-muted">Cancelar</button>}
      </div>
      <input className="border border-border rounded-lg px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre de la gráfica" />

      <select className="border border-border rounded-lg px-3 py-2 text-sm" value={chartType} onChange={(e) => setChartType(e.target.value as ChartType)}>
        {CHART_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>

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
          {rangeType === "fixed" && (
            <div className="flex flex-col gap-2">
              <input type="datetime-local" value={historicalFrom} onChange={(e) => setHistoricalFrom(e.target.value)} className="border border-border rounded px-2 py-1 text-xs" />
              <input type="datetime-local" value={historicalTo} onChange={(e) => setHistoricalTo(e.target.value)} className="border border-border rounded px-2 py-1 text-xs" />
            </div>
          )}
        </div>
      )}

      <SignalTreePicker source={dataMode === "live" ? "live" : "historical"} selected={signals} chartColor={color} onChange={setSignals} />

      <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-full" />

      <button onClick={submit} disabled={!name || signals.length === 0} className="bg-ink text-white rounded-lg py-2 text-sm font-bold disabled:opacity-40">
        {initial ? "Guardar cambios" : "+ Añadir al panel"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Wire `EditorPage`**

```typescript jsx
// frontend/src/pages/EditorPage.tsx
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingChart, setEditingChart] = useState<Chart | null>(null);

  const load = () => {
    setLoadError(null);
    if (id) api.dashboards.get(id).then(setDashboard).catch(() => setLoadError("No se pudo cargar el dashboard."));
  };

  useEffect(load, [id]);

  if (loadError) return <div className="p-8 text-danger">{loadError}</div>;
  if (!dashboard) return <div className="p-8">Cargando…</div>;

  const fail = () => window.alert("La operación falló. Inténtalo de nuevo.");

  const saveName = async (name: string) => {
    setDashboard({ ...dashboard, name });
    await api.dashboards.update(dashboard.id, { name }).catch(fail);
  };

  const saveDescription = async (description: string) => {
    setDashboard({ ...dashboard, description });
    await api.dashboards.update(dashboard.id, { description }).catch(fail);
  };

  const submitChart = async (chart: Omit<Chart, "id" | "dashboard_id">) => {
    if (editingChart) {
      await api.charts.update(editingChart.id, chart).then(load).then(() => setEditingChart(null)).catch(fail);
    } else {
      await api.charts.create(dashboard.id, chart).then(load).catch(fail);
    }
  };

  const removeChart = async (chartId: string) => {
    await api.charts.delete(chartId).then(load).catch(fail);
    if (editingChart?.id === chartId) setEditingChart(null);
  };

  const onLayoutChange = async (layout: { i: string; x: number; y: number; w: number; h: number }[]) => {
    for (const l of layout) {
      await api.charts.update(l.i, { layout_x: l.x, layout_y: l.y, layout_w: l.w, layout_h: l.h }).catch(fail);
    }
  };

  const publish = async () => {
    await api.dashboards.publish(dashboard.id).then(() => navigate(`/dashboards/${dashboard.id}`)).catch(fail);
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
        <ChartForm key={editingChart?.id ?? "new"} initial={editingChart ?? undefined} onSubmit={submitChart} onCancel={() => setEditingChart(null)} />
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
            <ChartRenderer
              dashboardId={dashboard.id}
              chart={chart}
              editable
              onRemove={() => removeChart(chart.id)}
              onEdit={() => setEditingChart(chart)}
            />
          )}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify everything typechecks and the full suite passes**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: no type errors; all test files pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/editor/ChartForm.tsx frontend/src/pages/EditorPage.tsx
git commit -m "feat(uns-dashboard): editing an existing chart reuses ChartForm and PATCHes it

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

### Task 15: Full regression + live verification

**Files:** none (verification only).

- [ ] **Step 1: Run both test suites**

Run: `cd backend && python -m pytest -v` (DB-gated tests will skip without `DATABASE_URL`/`HISTORIAN_DATABASE_URL` set — set both to a running stack to exercise them)
Run: `cd frontend && npx vitest run`
Expected: all non-skipped tests pass.

- [ ] **Step 2: Bring up the full stack and verify each enhancement live**

Run: `docker compose up -d` from the repo root (or `UNS_DASHBOARD/scripts/up.sh` if only this stack is needed, provided `UNS_MANAGER`/`UNS_HISTORIAN` are already running).

In a browser against the running editor, confirm each of the following, self-contained and independently checkable:

- **Signal tree**: opening the signal picker while `data_mode = live` shows a collapsible hierarchy sourced from currently-flowing topics; switching to `historical` re-fetches from the Historian and can show different/additional topics (anything with stored history but not currently publishing). An `_analytical` topic (publish one manually if none exist yet, e.g. `mosquitto_pub -t "Test/Line/_analytical" -m '{"Health_Score": 0.9, "timestamp": "2026-09-04T00:00:00Z"}'`) appears in both trees labeled `analytical`.
- **Chart colors + editing**: create a chart, set a chart color, add two signals with distinct per-signal colors — confirm both render distinctly (not both blue). Click "✎" on an existing chart, change its color and remove one signal, save — confirm the grid updates and a page reload shows the change persisted (PATCH round-trip).
- **Zoom**: on a timeseries chart with several points, drag across the chart body or use the bottom slider — confirm the visible range narrows; switching the chart's range/mode resets the zoom.
- **Streaming degraded mode**: `docker compose stop uns_dashboard_redis` (or the bridge) — within ~20s, a live chart's badge should read "Sin datos recientes" or "Reconectando…" instead of staying green. `docker compose start uns_dashboard_redis` — confirm it self-heals back to "Live" without a page reload.
- **Historical degraded mode**: stop the Historian's Postgres container — a historical chart should show "No se pudo cargar el histórico" with a "Reintentar" button instead of a blank/stale chart. Restart it and click "Reintentar" — confirm data returns.

- [ ] **Step 3: Update the README if any run/verification step changed**

Check `UNS_DASHBOARD/README.md` for an existing "smoke test" or "known limitations" section describing the old flat signal search or the old always-create chart form; update any such description to match the new tree picker and edit flow. If no such section exists, skip this step.

- [ ] **Step 4: Commit (only if Step 3 changed anything)**

```bash
git add UNS_DASHBOARD/README.md
git commit -m "docs(uns-dashboard): update README for signal tree and chart-edit flow

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B9vvkCFuBSPpUDT21VaeXk"
```

---

## Explicitly deferred (see design spec)

- A generic backend `/health` endpoint aggregating Redis/Historian reachability.
- Migrating `KpiTile`/`StatusIndicator`/`ValuesTable` to ECharts.
- Manual drag-reordering of signals within a chart.
