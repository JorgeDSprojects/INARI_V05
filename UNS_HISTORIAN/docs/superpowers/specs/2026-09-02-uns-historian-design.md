# UNS Historian — Ingestion Service Design Spec
**Date:** 2026-09-02
**Status:** Approved
**Scope:** First milestone — MQTT-to-TimescaleDB ingestion pipeline only (no query API, no frontend)

---

## Context

The UNS Manager publishes ISA-95-hierarchical MQTT topics (`enterprise/site/area/line/cell/asset/_descriptive` and `.../_informative`) to EMQX, all with `retain=true`. In addition, external data sources (Node-RED flows, simulators, PLCs) publish live process telemetry to the same `_informative` topics — wide JSON objects carrying many named signals per message plus their own event `timestamp`, e.g.:

```json
{
  "timestamp": "2026-09-02T13:23:24.902Z",
  "Gen_RPM_Max": 1025.2,
  "Gen_RPM_Min": 996.9,
  "Gen_Bear_Temp_Avg": 35,
  "Gen_SlipRing_Temp_Avg": 26
}
```

The corresponding `_descriptive` payload self-documents these signals (unit, data type, range, chart hints) under a `signals` object, but does not follow a project-wide fixed catalog — every cell/asset can define its own signal names.

The goal of this milestone: capture every MQTT message published under the UNS namespace into a durable, queryable time-series store (PostgreSQL + TimescaleDB), as an independently deployable Docker service, so that later milestones (query API, dashboards, LLM-based analysis) have real historical data to build on. This milestone is **ingestion and storage only** — no query API, no frontend, no retention/compression policy yet.

---

## Key Decisions (from clarifying questions)

| Decision | Choice |
|---|---|
| Scope of capture | Everything under the UNS namespace (subscribe `#` on EMQX) |
| Storage shape | Generic: full MQTT payload as JSONB per row (not exploded into per-signal rows) |
| Milestone scope | Ingestion + storage only; no query API, no frontend view |
| Retention/compression | None yet — keep everything, unlimited, revisit once real volume is known |
| Service location | New sibling folder `UNS_HISTORIAN/`, own `docker-compose.yml`, independently up/down-able |
| Database | New dedicated Postgres+TimescaleDB instance — **not** shared with UNS Manager's Postgres (which lacks the TimescaleDB extension) |
| Admin/verification tool | pgAdmin container included, for manually confirming ingestion works |
| Event timestamp | Each row's `time` comes from the payload's own `timestamp` field when present (accounts for batching/network delay); falls back to MQTT arrival time otherwise |
| Deduplication | Compare the full normalized payload (including any embedded `timestamp`) against the last stored value for that topic; skip insert if identical. This naturally suppresses EMQX's retained-message replay on reconnect (byte-identical repeat) without ever dropping genuine telemetry (which always carries a new `timestamp`) |

---

## Section 1 — Architecture

New sibling folder to `UNS_MANAGER/`: `UNS_HISTORIAN/`, with its own `docker-compose.yml`, `.env.example`, and `scripts/{up,down,restart,logs,status}.sh` (per repo's `AGENTS.md` service conventions). Deployable and removable independently of the UNS Manager stack.

Three containers:

- **`uns_historian_postgres`** — `timescale/timescaledb:latest-pg16`. Dedicated instance, separate from `UNS_MANAGER`'s `uns_postgres` (which is plain `postgres:16-alpine` without the TimescaleDB extension). Own named volume.
- **`uns_historian_pgadmin`** — `dpage/pgadmin4`, host-exposed (e.g. `5051:80`), for manual inspection/verification that ingestion is working. Pre-registered connection to `uns_historian_postgres` via a mounted `servers.json` where supported.
- **`uns_historian_ingestor`** — custom Python 3.12 service (`paho-mqtt` + `psycopg`). Subscribes to EMQX and writes to Postgres. No HTTP surface in this milestone (pure background worker).

Two Docker networks:

- **`uns_net`** — declared `external: true` (already created by `UNS_MANAGER/docker-compose.yml`). Only `uns_historian_ingestor` joins it, to reach `emqx:1883`. Requires `UNS_MANAGER` to be running first; documented in the historian's README.
- **`historian_net`** — internal bridge network, private to this stack. Connects `uns_historian_ingestor` ↔ `uns_historian_postgres` ↔ `uns_historian_pgadmin`, keeping the database off the shared UNS network.

```
UNS_MANAGER stack (uns_net)          UNS_HISTORIAN stack
┌─────────────┐                      ┌───────────────────────────────┐
│ emqx        │◄────subscribe #──────│ uns_historian_ingestor         │
│ (1883)      │                      │  (uns_net + historian_net)     │
└─────────────┘                      └──────────────┬──────────────────┘
                                                      │ historian_net
                                      ┌───────────────┴───────────────┐
                                      │ uns_historian_postgres         │
                                      │ (TimescaleDB)                  │
                                      └───────────────┬─────────────────┘
                                                      │ historian_net
                                      ┌───────────────┴───────────────┐
                                      │ uns_historian_pgadmin (host:5051)│
                                      └─────────────────────────────────┘
```

---

## Section 2 — Data Schema

Single hypertable, no per-signal normalization (YAGNI — no fixed signal catalog exists project-wide; the `_descriptive.signals` catalog documents units/ranges per cell but isn't a global schema).

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE mqtt_messages (
    time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,
    payload      JSONB,
    raw_payload  TEXT,
    qos          SMALLINT NOT NULL,
    retain       BOOLEAN NOT NULL
);

SELECT create_hypertable('mqtt_messages', 'time');
CREATE INDEX idx_mqtt_messages_topic_time ON mqtt_messages (topic, time DESC);
```

- **`payload`**: parsed JSON body of the reading (see Section 3 for how list-wrapped/multi-reading messages are split into individual rows).
- **`raw_payload`**: original text, populated only when JSON parsing fails; `payload` is `NULL` in that case.
- **Empty payload** (e.g. `clear_retained()` in the UNS Manager backend publishes an empty body to clear a retained topic on delete/rename): stored as a row with `payload = NULL`, `raw_payload = NULL` — represents a real "topic cleared" event, useful for traceability.
- This schema deliberately does not attempt to identify or type individual signals (`Gen_RPM_Avg`, etc.) — a future query layer can extract them ad hoc (`payload->>'Gen_RPM_Avg'`) or a materialized view/expression index can be added later without touching ingestion or already-stored data.

Example query (validated against the real payload shapes above), for future reference — **not implemented in this milestone**:

```sql
SELECT time, (payload->>'Gen_Bear_Temp_Avg')::numeric AS temp
FROM mqtt_messages
WHERE topic = 'enterprise1/site1/areaA/line1/genCell/_informative'
  AND time BETWEEN '2026-08-01' AND '2026-09-01'
ORDER BY time;
```

---

## Section 3 — Ingestion Logic

Single Python process (`uns_historian_ingestor`), no web framework needed.

1. **Startup**: connect to `uns_historian_postgres`. Schema is created via an `init.sql` mounted at `/docker-entrypoint-initdb.d/` (runs once, only on first boot with an empty volume).
2. **Dedup cache warm-up**: `SELECT DISTINCT ON (topic) topic, payload, raw_payload FROM mqtt_messages ORDER BY topic, time DESC` seeds an in-memory `{topic: last_normalized_payload}` dict. Required so that a service restart doesn't reinsert unchanged retained messages replayed by EMQX on reconnect.
3. **MQTT connection**: `paho-mqtt`, `client_id=uns-historian-ingestor`, subscribes to `#` at QoS 1, with `reconnect_delay_set` for automatic reconnect/backoff. (Per MQTT spec, a `#` subscription does not receive EMQX's `$SYS/...` topics — no manual filtering needed.)
4. **`on_message` → normalize to one or more readings**:
   - Decode payload bytes (UTF-8, replace on error) and attempt `json.loads`.
   - If parsing fails: one reading, `payload=None`, `raw_payload=<decoded text>`, `time=<arrival time>`.
   - If the JSON is a list: iterate each element as its own reading (handles Node-RED's array-of-readings batching).
   - If the JSON is a single object: treated as one reading.
   - For each reading (object): if it has a parseable `timestamp` key (ISO 8601, `Z` suffix handled), use it as `time`; otherwise fall back to MQTT arrival time. The object is stored as-is in `payload` (including its own `timestamp` key, if present — kept for completeness, not stripped).
5. **Dedup check per reading**: compare the reading's normalized `payload` (or `raw_payload` if JSON parsing failed) against the cache entry for `topic`. If identical, drop it (no insert, no cache update). Otherwise, update the cache and append `{time, topic, payload, raw_payload, qos, retain}` to an in-memory flush buffer.
   - This single rule handles both real cases correctly: an EMQX retained-message replay on reconnect is a byte-identical repeat (same embedded `timestamp` too) and gets dropped; a genuine new telemetry reading always carries a different `timestamp`, so it's never mistaken for a duplicate even if all signal values happen to repeat.
   - **Known limitation** (acceptable for this milestone): if a data source ever publishes readings *without* an embedded `timestamp` and with byte-identical content back-to-back, those readings collapse into a single stored row. No such source exists in the current UNS Manager or Node-RED flows.
6. **Flush loop**: every ~2s or when the buffer reaches ~500 rows (whichever first), batch-insert via `execute_values` and clear the buffer. On a Postgres error: log it, keep the buffer, retry with backoff. Cap the buffer (e.g. 20,000 rows); if Postgres stays unreachable long enough to hit the cap, drop the oldest entries with a warning log rather than growing unbounded.
7. **Logging**: structured logs for connect/disconnect/subscribe, flush counts, drops, and errors (per `AGENTS.md` observability baseline).

---

## Section 4 — Deployment

- `UNS_HISTORIAN/docker-compose.yml` — the three services described in Section 1.
- `UNS_HISTORIAN/.env.example` documents: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`, `EMQX_HOST` (default `emqx`, matching `UNS_MANAGER`'s container name), `EMQX_PORT` (default `1883`), `MQTT_TOPIC_FILTER` (default `#`), `FLUSH_INTERVAL_SECONDS`, `FLUSH_MAX_ROWS`, `BUFFER_MAX_ROWS`.
- `UNS_HISTORIAN/scripts/{up,down,restart,logs,status}.sh` following the same pattern as any other service in this repo.
- `uns_historian_ingestor/Dockerfile` — `python:3.12-slim` base, installs `paho-mqtt` and `psycopg[binary]`.
- README note: `UNS_MANAGER` must be running first (`uns_net` must already exist and EMQX must be reachable), since `uns_net` is referenced as `external: true`.

---

## Section 5 — Testing

- **Unit tests** (no live broker/DB required):
  - Message-to-reading(s) normalization: single object, list of objects, non-JSON payload, empty payload, missing/invalid `timestamp` field (fallback to arrival time).
  - Dedup cache decision logic: new topic, unchanged payload, changed payload (including the "same values, different embedded timestamp" case).
- **Manual verification**: `docker compose up`, trigger a real change from the UNS Manager UI (or `mosquitto_pub` for a synthetic message), confirm the corresponding row appears in `mqtt_messages` via pgAdmin.
- **Out of scope for this milestone**: automated integration tests against a live EMQX/Postgres pair. Documented as a follow-up once the query/API milestone introduces a testable HTTP surface.

---

## Explicitly deferred (future milestones)

- Query/REST API over `mqtt_messages`.
- UNS Manager frontend view for historical trends.
- Retention and compression policies (TimescaleDB native compression, drop-after-N-days).
- Per-signal structured extraction (materialized views or expression indexes keyed off the `_descriptive.signals` catalog), once/if a project-wide signal-naming convention is needed.
- Correlating `mqtt_messages` rows back to UNS Manager's own Postgres entities (enterprise/site/.../asset) by topic.
