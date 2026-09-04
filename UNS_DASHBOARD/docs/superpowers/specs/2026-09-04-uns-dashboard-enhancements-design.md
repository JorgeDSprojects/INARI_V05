# UNS Dashboard — Enhancements Design Spec (v1.1)
**Date:** 2026-09-04
**Status:** Approved
**Scope:** Four fixes/enhancements to the shipped v1 (`2026-09-03-uns-dashboard-design.md`), found while using the editor hands-on: a hierarchical signal picker, a color bug + missing chart-edit UI, a chart-library migration for native zoom, and degraded-mode UX when streaming or the Historian is unavailable.

---

## Context

v1 shipped with a flat, prefix-search signal picker; single-color-always-blue charts with no way to edit a chart once added to the grid; a hand-rolled `recharts` timeseries with no zoom; and silent failure modes when Redis/EMQX or the Historian are unreachable. This spec addresses all four, plus introduces a third topic type this milestone needs to account for: `_analytical` (KPIs computed and published by *other* services, never by `UNS_MANAGER`, so it never exists in `UNS_MANAGER`'s Postgres — only ever observable on the wire).

---

## Key Decisions

| Decision | Choice |
|---|---|
| `_analytical` topics | Third payload type alongside `_descriptive`/`_informative`. Never in `UNS_MANAGER`'s DB. Bridged live and stored by the Historian exactly like `_informative` (both are flat JSON + `timestamp`). |
| Signal picker | Replaces the flat prefix search with a collapsible **hierarchy tree** (folders = topic path segments, leaves = `_informative`/`_analytical` topics with their signal keys). |
| Tree data source | **Dual**, chosen by the chart's `data_mode`: `historical` charts browse the **Historian** (`mqtt_messages`); `live` charts browse **Redis** (`live:<topic>` stream keys, the bridge's own mirror of EMQX). Never queries EMQX's admin API for topic discovery — its `/api/v5/topics` only reflects subscriptions (our bridge subscribes with one wildcard `#`), not per-topic publish activity. This also means a Historian outage never blocks building/viewing a live chart, and vice versa. |
| Charting library | Migrate **timeseries, gauge, bar** to `echarts` (native `dataZoom` for zoom/pan, native gauge). **KPI tile, status indicator, values table** stay plain React/HTML — they aren't charts, so a charting library adds no value there. `recharts` is dropped entirely once the three are migrated. |
| Chart editing | New shared create/edit form; editing an existing chart calls the already-fully-capable `PATCH /charts/{id}` (unused for this until now) instead of only ever `POST`ing new charts. |
| Per-chart vs per-signal color | One resolution rule: `signal.color` override → else `chart.color` if the chart has exactly one signal → else a rotating palette by signal index. Replaces today's "always blue" fallback without two disconnected color systems. |
| Streaming degraded mode | Frontend-only: track last-frame time per topic; a chart's "Live" badge turns "Sin datos recientes" (stale > 15s) or "Reconectando…" (WS not open) instead of showing green with no data. No backend protocol change. |
| Historical degraded mode | `useHistoricalQuery` returns `{points, error, retry}`; a failed fetch shows an inline error + manual retry instead of a silently blank/stale chart. Relative-range charts still self-heal on their next scheduled poll. |
| Backward compatibility | `/signals/catalog` and `SignalPicker.tsx` are retired (fully superseded by the tree), not kept alongside the new picker — avoids maintaining two parallel signal-lookup paths. |

---

## Section 1 — Signal Tree Picker

### Backend

- **Bridge** (`filter.py`): `is_informative_topic` → `is_bridgeable_topic`, matching last segment `_informative` **or** `_analytical`. Without this, analytical signals would never reach Redis and couldn't power live charts or the live tree.
- **Historian side stays untouched** — it already subscribes to `#` and stores everything, `_analytical` included.
- **`GET /signals/tree/historical?topic_prefix=`** (backend, replaces `/signals/catalog`): distinct topics from `mqtt_messages` matching `_informative`/`_analytical` (same `ESCAPE '\'`-safe prefix filter as today), split each on `/`, assembled server-side into a nested tree. Leaf keys come from the latest stored payload, same as today's catalog logic.
- **`GET /signals/tree/live`**: `SCAN` (not `KEYS`, to avoid blocking Redis) for `live:*`, strip the prefix to recover each topic, filter to `_informative`/`_analytical`, build the same nested shape. Leaf keys come from one `XREVRANGE <stream> + COUNT 1` per topic (latest payload's fields).
- Shared response shape:
  ```jsonc
  // array of top-level nodes; each node either has children (folder) or a leaf (topic)
  [{
    "segment": "Planta1",
    "children": [{
      "segment": "Linea3",
      "children": [{
        "segment": "_informative",
        "children": [],
        "leaf": { "topic": "Planta1/Linea3/_informative", "topic_type": "informative", "keys": ["Gen_RPM_Avg", "Amb_Temp_Avg"] }
      }]
    }]
  }]
  ```
- `/signals/descriptive` is unchanged — still a one-off lookup on add, still always overridable.

### Frontend

- New `SignalTreePicker.tsx` (replaces `SignalPicker.tsx`), taking `source: "historical" | "live"` (derived from the chart form's current `data_mode`) and rendering collapsible folders down to leaf topics; each leaf shows an `informative`/`analytical` badge and its keys as "+ add" buttons, same interaction as today's flat list. A failed tree fetch shows an inline error scoped to that picker only — it never blocks the other `data_mode`'s picker, since a chart is always exclusively live or historical.

---

## Section 2 — Chart Colors & Editing

**Root cause (confirmed in code):** `chart.color` is persisted but never read by any chart renderer. Multi-signal charts read `ChartSignal.color`, which the UI never sets — so it's always `undefined`, falling back to one hardcoded blue everywhere. Separately, there is no edit UI at all: `ChartForm` only ever creates; the backend's `PATCH /charts/{id}` (which already fully replaces signals) is only ever called for layout drag/resize.

**Fixes:**

- One color-resolution rule, used everywhere a signal needs a color: `signal.color` (explicit override) → else, if the chart has exactly one signal, `chart.color` → else, a rotating default palette (~8 hues) by signal index. This makes gauge/kpi/status/single-signal-bar governed by the one color you set in the form, while multi-signal timeseries/bar get distinct colors out of the box instead of one hardcoded blue, without two disconnected color systems.
- Each resolved color remains editable via a swatch next to the signal chip in `SignalTreePicker`'s selected-signals strip — editing it sets an explicit `signal.color` override.
- `ChartForm` gains an optional `initial: Chart` prop; when set, it pre-fills every field (name, type, signals+colors, data mode/range, chart color) and submits via `api.charts.update` (PATCH) instead of `api.charts.create` (POST).
- `ChartCardShell` gains an "✎ editar" button (visible only when `editable`), which tells `EditorPage` which chart to load into the sidebar form in edit mode. Only one chart is editable at a time; saving or cancelling returns the sidebar to create mode.

---

## Section 3 — Charting Library Migration (ECharts)

- Add `echarts` + `echarts-for-react`.
- **`TimeSeriesChart`**: ECharts `line` series (area-filled), `dataZoom: [{type:"inside"}, {type:"slider"}]` for wheel/pinch/drag-to-zoom. Re-renders on new `option` when the underlying `points` identity changes (chart/range switch), so zoom state naturally resets — no bespoke reset logic needed.
- **`GaugeChart`**: ECharts native `gauge` series — picks up needle, banding, min/max from the signal's `min`/`max`/`unit` for free (a visual upgrade vs. the current hand-rolled version).
- **`BarChart`**: ECharts `bar` series, one bar per signal, colored via the same color-resolution rule as timeseries (Section 2).
- **`KpiTile`, `StatusIndicator`, `ValuesTable`**: explicitly **not** migrated — a single number, a colored dot, and a table are not chart-shaped problems; ECharts would be pure overhead. Kept as plain React, `chart.color` wired in per Section 2.
- `recharts` and its `ResizeObserver` jsdom polyfill are removed once TimeSeriesChart/GaugeChart/BarChart no longer use it; ECharts under jsdom needs a canvas-context stub instead (see Testing).

---

## Section 4 — Degraded-Mode UX (Streaming / Historian Outages)

Today: a Redis/EMQX outage leaves a WS connection open but silently mute (frontend can't tell "no news" from "broken"); a Historian outage is caught and swallowed with no user-visible sign at all.

- **`useDashboardSocket`** additionally tracks `lastFrameAt` per topic and an overall `wsState: "connecting"|"open"|"reconnecting"`. A topic counts as **stale** once `now - lastFrameAt > 15s` (well above the ~155ms live latency already measured end-to-end).
- **`ChartCardShell`** badge logic (live charts only): `open` + fresh → "Live · tiempo real" (green, unchanged); `open` + stale → "Sin datos recientes" (amber); not `open` → "Reconectando…" (red). Self-heals the moment frames resume — no manual action needed.
- **`useHistoricalQuery`** returns `{points, error, retry}` instead of a bare array. On `error` with no cached points yet, the chart shows "No se pudo cargar el histórico" + a "Reintentar" button; if stale points already exist, they stay visible with a small warning badge rather than going blank. `relative`-range charts already retry automatically on their next scheduled poll; `fixed`-range charts (one-shot) rely on the manual retry button.
- The two signal-tree endpoints (Section 1) already fail independently by construction — a chart is always exclusively live or historical, so an outage in one data source is never visible while authoring the other kind of chart.
- This is the same "independence per component" principle the v1 spec already established for `data_mode` — applied here to failure isolation, not just configuration.

---

## Testing

- **Bridge**: `is_bridgeable_topic` unit-tested for `_informative`/`_analytical`/neither.
- **Backend**: tree-building function (topic-list → nested structure) unit-tested with fixtures covering mixed depths and both topic types, independent of any live DB/Redis; `/signals/tree/live`'s Redis `SCAN`+`XREVRANGE` glue is thin I/O, verified live only (per existing testing philosophy).
- **Frontend**: `SignalTreePicker` tree-building/rendering logic unit-tested with mock catalogs; palette-assignment function unit-tested; `useDashboardSocket`'s staleness computation unit-tested with fake timers; `useHistoricalQuery`'s error/retry state unit-tested. Chart components get a minimal ECharts smoke render (mocking `getContext` for jsdom, replacing the old `ResizeObserver` polyfill).
- **Manual/live verification**: chart edit round-trip (color change + add/remove signal persists), zoom interaction, and pulling the plug on Redis and on the Historian independently to confirm each degraded-mode badge/message appears and self-heals — same headless-browser technique used throughout v1.

---

## Explicitly deferred

- Server-push staleness detection (backend tracking Redis/EMQX health itself) — the frontend's last-frame-age heuristic is sufficient and keeps the backend simpler.
- A generic `/health` endpoint aggregating Redis/Historian reachability — per-request error handling already gives each chart its own accurate status; a dashboard-wide banner isn't needed yet (YAGNI).
- Migrating KPI/status/table to ECharts "for consistency" — deliberately rejected, see Section 3.
- Manual drag-reordering of signals within a chart (order stays insertion order, unchanged from v1).
- Charting two signals that share the same `signal_key` from different topics on one chart: they currently collide (last one wins, both series render identically) since points are keyed by bare `signal_key`, not `(topic, signal_key)`. Pre-existing since v1; fixing it touches `historian_query.py`'s point shape and every chart component's `dataKey` end-to-end, so deferred rather than bundled into this round's fixes.
