# UNS Dashboard — Real-Time SCADA Visualization Design Spec
**Date:** 2026-09-03
**Status:** Approved
**Scope:** v1 — dashboard authoring (menu, editor, viewer), live streaming pipeline, historical backfill/query, 6 chart types. No auth, no alerting, no dashboard versioning.

---

## Context

`UNS_MANAGER` publishes ISA-95 hierarchical topics to EMQX: `.../_descriptive` (asset metadata, retained) and, from Node-RED flows and simulators, `.../_informative` — wide flat JSON objects carrying many named signals plus their own `timestamp`, e.g.:

```json
{
  "timestamp": "2026-09-02T13:23:24.902Z",
  "Gen_RPM_Avg": 1342.1,
  "Gen_Bear_Temp_Avg": 58,
  "Amb_Temp_Avg": 19
}
```

`UNS_HISTORIAN` already subscribes to `#` on EMQX and persists every message verbatim into a TimescaleDB hypertable (`mqtt_messages(time, topic, payload jsonb, raw_payload, qos, retain)`), with no per-signal schema — durability and "never lose a message" are already solved there.

The goal of this milestone: a new independently deployable module, `UNS_DASHBOARD/`, that lets a user author SCADA-style dashboards (drag/resize widgets via react-grid-layout), each widget bound to one or more `_informative` signals, either streaming live or querying a historical window, and publish them to a read-only production view. Three UI screens were mocked up in pencil.dev before this spec: **01 Menu Dashboards**, **02 Editor**, **03 Viewer (modo visualización)**.

---

## Key Decisions (from clarifying questions)

| Decision | Choice |
|---|---|
| Real-time transport | `EMQX → bridge (MQTT subscriber) → Redis Streams (bounded buffer) → dashboard backend WebSocket → browser`. The browser never speaks MQTT directly. |
| Why not Kafka | End-to-end durability is already guaranteed by `UNS_HISTORIAN`. Redis Streams only smooths short dashboard-side outages; Kafka's operational weight (ZK/KRaft, partitions, retention policy) isn't justified at this scale (YAGNI). |
| Why not direct browser MQTT-over-WebSocket | Keeps broker credentials/ACLs out of the browser and centralizes fan-out/backpressure to many browser tabs in one backend WS layer instead of many direct EMQX connections. |
| Future ML/agent consumers | Any future consumer (ML model, alerting) subscribes **directly to EMQX**, never to `UNS_DASHBOARD`'s Redis. Redis here is a private implementation detail of this module's live-delivery path, not a shared bus — this keeps `UNS_DASHBOARD` independently deployable, consistent with how `UNS_MANAGER` and `UNS_HISTORIAN` already work standalone. |
| Historical backfill | On chart load, initial data comes from a read-only cross-stack query against `UNS_HISTORIAN`'s `mqtt_messages`, downsampled via `time_bucket` to a manageable point count. |
| Data-mode granularity | Per **component** (chart), not per dashboard. Each chart independently is `live` or `historical`. |
| Historical range types | `fixed` (explicit from/to, static snapshot, never auto-refreshes) or `relative` (rule: last hour / 24h / week / month; re-queried on an interval since the window moves with time). |
| Chart types v1 | Time series (line/area), gauge, KPI tile, bar, table of live values, status indicator (LED). |
| Persistence | Own Postgres database for dashboard/chart definitions — mirrors the existing per-stack pattern (`UNS_MANAGER` and `UNS_HISTORIAN` each own their database). |
| Signal metadata | Best-effort prefill from the topic's retained `_descriptive` message (its optional `signals` map) when the key matches; always manually overridable per signal (label/unit/range/color) since `_descriptive.signals` is not a guaranteed project-wide catalog. |
| Cross-stack coupling | Only two: EMQX (already shared) and `UNS_HISTORIAN`'s Postgres (read-only, for history + signal discovery). No direct dependency on `UNS_MANAGER`'s Postgres — descriptive metadata is read live off EMQX's retained message instead. |
| Auth | None in v1, consistent with `UNS_MANAGER`/`UNS_HISTORIAN`. |

---

## Section 1 — Architecture

New sibling folder `UNS_DASHBOARD/`, own `docker-compose.yml`, `.env.example`, and `scripts/{up,down,restart,logs,status}.sh` per `AGENTS.md`. Independently deployable, included from the root `docker-compose.yml` alongside the other two stacks.

Five containers:

- **`uns_dashboard_postgres`** — `postgres:16-alpine`. Own instance, dashboard/chart definitions only.
- **`uns_dashboard_redis`** — `redis:7-alpine`. Live-data buffer, private to this stack.
- **`uns_dashboard_bridge`** — Python (`paho-mqtt`), background worker. Subscribes to EMQX (`#`, QoS 1, persistent session), filters topics ending in `_informative`, `XADD`s each reading to a per-topic Redis Stream (`live:<topic>`, `MAXLEN ~1000`).
- **`uns_dashboard_backend`** — FastAPI. Dashboard/chart CRUD, signal catalog, historical query endpoint, and a WebSocket endpoint that multiplexes Redis Stream reads to connected browsers.
- **`uns_dashboard_frontend`** — React + `react-grid-layout`, the three mocked-up screens.

Two Docker networks:

- **`uns_net`** — the existing external network shared with `UNS_MANAGER` (EMQX) and `UNS_HISTORIAN`. Joined by `uns_dashboard_bridge` (to reach `emqx:1883`) and `uns_dashboard_backend` (to reach `uns_historian_postgres:5432` for history/catalog reads). This requires one small addition to `UNS_HISTORIAN/docker-compose.yml`: attach `uns_historian_postgres` to `uns_net` in addition to its own private `historian_net`, the same way its ingestor already joins `uns_net` to reach EMQX.
- **`dashboard_net`** — internal bridge network, private to this stack. Connects `uns_dashboard_backend` ↔ `uns_dashboard_postgres` ↔ `uns_dashboard_redis` ↔ `uns_dashboard_bridge` (bridge↔redis only, no direct DB access).

```
UNS_MANAGER (uns_net)         UNS_HISTORIAN                    UNS_DASHBOARD
┌─────────────┐               ┌─────────────────────┐          ┌─────────────────────────┐
│ emqx        │◄──subscribe#──┤ uns_historian_       │          │ uns_dashboard_bridge     │
│ (1883)      │◄──subscribe#──┼─ingestor             │    ┌─────┤  (uns_net + dashboard_net)│
└─────────────┘               └──────────┬───────────┘    │     └───────────┬─────────────┘
                                          │ historian_net  │                 │ dashboard_net
                               ┌──────────┴───────────┐    │     ┌───────────┴─────────────┐
                               │ uns_historian_postgres │◄──┘     │ uns_dashboard_redis      │
                               │ (also joins uns_net)  │  read-   └───────────┬─────────────┘
                               └───────────────────────┘  only                │ dashboard_net
                                                                    ┌──────────┴─────────────┐
                                                                    │ uns_dashboard_backend    │
                                                                    │ (WS + REST)              │
                                                                    └──────────┬─────────────┘
                                                                               │ dashboard_net
                                                                    ┌──────────┴─────────────┐
                                                                    │ uns_dashboard_postgres   │
                                                                    └─────────────────────────┘
```

---

## Section 2 — Data Model (`uns_dashboard_postgres`)

```sql
dashboards
  id, name, description, status ('draft'|'published'),
  created_at, updated_at, published_at

charts
  id, dashboard_id (FK → dashboards),
  name, description,
  chart_type ('timeseries'|'gauge'|'kpi'|'bar'|'table'|'status'),
  data_mode ('live'|'historical'),
  historical_range_type ('fixed'|'relative', nullable — only when data_mode='historical'),
  historical_from timestamptz (nullable, 'fixed' only),
  historical_to timestamptz (nullable, 'fixed' only),
  historical_relative_rule text (nullable, 'relative' only — '1h'|'24h'|'7d'|'30d'|custom 'Nh'/'Nd'),
  layout_x, layout_y, layout_w, layout_h int (react-grid-layout position/size),
  color text,
  config jsonb (chart-type-specific extras, e.g. gauge min/max, decimals),
  created_at, updated_at

chart_signals
  id, chart_id (FK → charts),
  topic text, signal_key text,
  label text, unit text, color text,
  min numeric (nullable), max numeric (nullable),
  source ('auto'|'manual') -- 'auto' = copied from _descriptive at add-time, 'manual' = user-entered/overridden
```

A chart's signal list order matters for legends/table rows — `chart_signals` carries an implicit order via its own `id`/insertion order; no separate `position` column needed at this scale (YAGNI).

---

## Section 3 — Real-Time Pipeline

1. **Bridge startup**: connects to EMQX with `client_id=uns-dashboard-bridge`, persistent session (`clean_session=False`), subscribes `#` at QoS 1. Persistent session means a bridge restart doesn't lose messages published while it was down, up to EMQX's session-expiry window.
2. **Filtering**: in `on_message`, only topics whose last segment is `_informative` are processed (mirrors the convention already used by `UNS_MANAGER`/Node-RED); everything else is dropped without further work.
3. **Buffering**: each reading is `XADD`ed to `live:<topic>` with `MAXLEN ~ 1000` (approximate trimming, cheap). One stream per topic keeps consumer offsets independent per signal source.
4. **Backend WebSocket**: one WS connection per open dashboard (view or edit). On connect, the client sends `{"subscribe": ["<topic>", ...]}` for every topic used by `live`-mode charts on that dashboard. The backend keeps one `XREAD BLOCK` loop per unique topic (shared across browser connections watching the same topic) and fans out `{"topic": ..., "time": ..., "payload": {...}}` frames to every subscribed WS client.
5. **Reconnect/catch-up**: the backend tracks the last Redis stream ID delivered to each WS client. On reconnect within the buffer window, it resumes from that ID (no gap). If the gap exceeds what the trimmed stream still holds, the backend does not attempt partial catch-up from Redis — the frontend instead re-issues a historical query (Section 4) for the missed window and appends it before resuming live tail.
6. **Browser reconnect**: standard WS client with exponential backoff; on reconnect, re-sends the same `subscribe` message.

---

## Section 4 — Historical Query Pipeline

- `GET /charts/{id}/history` — computes the effective `[from, to]` range server-side (never trusts a client-supplied "now" for `relative` rules, to avoid clock skew), queries `uns_historian_postgres.mqtt_messages` filtered by `topic IN (...)` and the time range, and extracts each configured `signal_key` via `payload->>'<key>'`.
- **Downsampling**: server picks a `time_bucket` width targeting ~500–1000 points across the requested range (e.g. a 1-hour range buckets at ~5s, a 30-day range at ~1h), so the payload size and render cost stay flat regardless of range length. Exact bucket width is `range_seconds / 750`, snapped to a sane rounded unit (1s/5s/30s/1m/5m/1h/1d).
- **Refresh cadence for `relative` charts** (frontend polls this same endpoint on an interval, not WS):

  | Rule | Poll interval |
  |---|---|
  | 1h | 30s |
  | 24h | 2 min |
  | 7d | 5 min |
  | 30d | 10 min |

- **`fixed`-range charts** call this endpoint once on load and never re-poll — a static snapshot by design.

---

## Section 5 — Signal Catalog & Manual Override

- `GET /signals/catalog?topic_prefix=<prefix>` — queries `uns_historian_postgres.mqtt_messages` for distinct topics under the given prefix ending in `_informative`, and for each, the JSON keys of its most recent stored payload (excluding `timestamp`). This is what populates the "Señales" picker in the editor.
- **Metadata prefill**: when a signal is added to a chart, the backend does a one-off retained-message lookup on `<topic-without-_informative>/_descriptive` via EMQX's REST API (same mechanism `UNS_MANAGER`'s `broker_service.list_retained_topics_by_prefix` already uses). If that payload has a `signals[<key>]` entry with `unit`/`range`, it prefills `chart_signals.unit`/`min`/`max` with `source='auto'`. This is best-effort only — `_descriptive.signals` is not a guaranteed schema — so every field stays freely editable, and editing one flips `source` to `'manual'`.
- This keeps `UNS_DASHBOARD` from ever connecting directly to `UNS_MANAGER`'s Postgres — descriptive metadata is read live off EMQX, not from another stack's database.

---

## Section 6 — Frontend

Three routes, matching the pencil.dev mockups:

- **Menu** (`/`) — lists dashboards (name, description, last published, draft/published status), View/Edit/Delete actions, "Nuevo dashboard".
- **Editor** (`/dashboards/:id/edit`) — left sidebar (dashboard name/description; per-chart form: name, description, chart type, signal picker with manual-override fields, data source live/historical toggle, and for historical the fixed/relative sub-form; color; "Añadir al panel") plus a `react-grid-layout` workspace where added charts are dragged/resized. "Publicar dashboard" sets `status='published'` and snapshots the current layout.
- **Viewer** (`/dashboards/:id`) — the published layout rendered read-only (no drag/resize/remove affordances), each chart independently wired to either the live WebSocket or the historical polling endpoint per its own `data_mode`.

Chart rendering components are shared between Editor (live preview while configuring) and Viewer, parameterized only by an `editable` flag that hides the drag handle/remove icon — never a separate rendering implementation.

---

## Section 7 — Deployment

- `UNS_DASHBOARD/docker-compose.yml` — the five services from Section 1.
- `UNS_DASHBOARD/.env.example`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `REDIS_HOST`/`REDIS_PORT`, `EMQX_HOST` (default `emqx`), `EMQX_PORT` (default `1883`), `EMQX_API_PORT` (default `18083`, for the retained-message lookup), `HISTORIAN_DATABASE_URL` (points at `uns_historian_postgres`), `STREAM_MAXLEN`, `VITE_API_BASE_URL`.
- `UNS_DASHBOARD/scripts/{up,down,restart,logs,status}.sh`, matching `UNS_HISTORIAN`'s pattern.
- Root `docker-compose.yml` gains a third `include:` entry for `UNS_DASHBOARD/docker-compose.yml`.
- One small modification to `UNS_HISTORIAN/docker-compose.yml`: `uns_historian_postgres` additionally joins `uns_net` (external), so `uns_dashboard_backend` can reach it by container DNS name. Documented in both stacks' READMEs, matching the existing "requires `UNS_MANAGER` running first" note pattern.

---

## Section 8 — Testing

- **Bridge** (unit): `_informative` suffix filtering, reading→Redis `XADD` payload shape, reconnect/persistent-session behavior (mockable).
- **Backend** (unit): historical range resolution (`relative` rule → `[from,to]`), `time_bucket` width selection, WS subscribe/fan-out multiplexing logic, signal catalog query, `_descriptive` prefill best-effort parsing (including when `signals` is absent/malformed).
- **Frontend**: chart renderer components tested with mock data for each of the 6 types (live and historical), editor form validation (required fields, range validation for `fixed`).
- **Integration**: end-to-end smoke test publishing a synthetic `_informative` message to EMQX and asserting it arrives over the dashboard WS; historical query against seeded `mqtt_messages` rows in a test Postgres.

---

## Explicitly deferred (future milestones)

- Authentication/authorization, multi-user concurrent editing/locking.
- Alerting/thresholds beyond the static-color status indicator (no notification pipeline).
- Chart types requiring aggregation beyond simple `time_bucket` averaging (histogram, scatter, heatmap).
- A shared multi-consumer message bus (Kafka) — revisit only if a future consumer needs durable replay across days, not just live tailing.
- Dashboard versioning/rollback of published layouts.
- Mobile/responsive viewer layout (v1 targets desktop SCADA screens, matching `react-grid-layout`'s fixed-grid model).
- Export/print/PDF snapshot of a dashboard.
