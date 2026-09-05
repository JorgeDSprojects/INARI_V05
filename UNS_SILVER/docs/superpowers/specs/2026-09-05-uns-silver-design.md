# UNS Silver — Bronze→Silver Normalization & Semantic Layer Design Spec
**Date:** 2026-09-05
**Status:** Draft — pending user review
**Scope:** First milestone — normalize `UNS_HISTORIAN`'s bronze JSONB into a queryable, typed, semantically-cataloged silver layer. Foundation for future LLM/agent consumers (out of scope here) and eventual dashboard integration (out of scope here).

---

## Context

`UNS_HISTORIAN` durably captures every MQTT message under the UNS namespace as raw JSONB (`mqtt_messages(time, topic, payload, raw_payload, qos, retain)`) — deliberately unopinionated about signal structure, by design (its own spec: *"no fixed signal catalog exists project-wide"*).

At the target scale — 1000+ individual topics, publish frequencies from 0.3s to 5s — this bronze shape is unusable as a direct substrate for LLM agents or fast historical queries: no per-signal typing, no units, no distinction between a physical sensor reading and a computed KPI, and no way to answer "what does this value mean" without re-parsing `_descriptive` on every query.

This milestone builds `UNS_SILVER`, a new independently deployable module that normalizes bronze into:
- A **versioned semantic catalog** (what each signal/KPI is: unit, type, range, thresholds, and how that definition changed over time).
- **Typed, per-signal time-series rows** (`silver_readings`) instead of wide JSONB blobs.
- A **per-element event log** (`silver_events`) for array-shaped occurrences (alarms, failure events) that don't fit a scalar time series.
- A **latest-value cache** for O(1) "current value" lookups.
- **Retention + continuous aggregates**, required at this scale (bronze's "keep everything, unlimited" decision does not carry over — see Section 4).

This spec covers ingestion/normalization only. KPI *computation* (formulas, health scores, business targets) is explicitly out of scope — those values are produced by an external script/service and published to MQTT; Silver only ingests and catalogs whatever arrives, regardless of source.

---

## Key Decisions (from clarifying questions)

| Decision | Choice |
|---|---|
| Data source | Read-only from `uns_historian_postgres` (bronze). No direct EMQX subscription — avoids re-solving MQTT reconnect/session/dedup concerns already solved once in `UNS_HISTORIAN`, and matches the use case's actual latency needs (chat/dashboard/KPI queries, not a control loop) |
| Freshness mechanism | Postgres `LISTEN/NOTIFY` (near-instant wake-up) with a polling fallback (crash/restart safety), not a fixed poll-only cadence |
| Current-value queries | Dedicated `silver_latest_value` upsert table — O(1) lookup, avoids `ORDER BY time DESC LIMIT 1` scans on every agent "what's the value now" question |
| KPI computation | Out of scope. An external service computes and publishes KPI values; Silver treats a KPI value exactly like a raw signal value — ingest, type, catalog. Never evaluates formulas |
| Topic structure | `_descriptive` gains a new `analytical` key (sibling to `signals`) holding KPI/analytics *definitions* (thresholds, unit, description, `version`, `effective_since`) — mirrors how `signals` documents raw physical signals. The existing `_analytical` topic is repurposed to carry **only values** (no thresholds/version embedded), mirroring `_informative`'s role for raw signals |
| Semantic catalog | Versioned with history (`effective_since`/`effective_until` per definition), not overwrite-in-place — enables correct historical threshold/range evaluation (e.g. "was this in alarm under the rules active *then*") |
| Payload shape handling | Generic recursive flattener, not a per-shape parser — required because analytical payloads vary by hierarchy level (asset alarm status vs. fleet business targets vs. site regulatory compliance) and are not a stable project-wide schema. See Section 3 |
| Uncataloged signals | Never dropped. Ingested and tagged `signal_type='unknown'` when no matching catalog definition exists |
| Retention/compression | Applies to Silver's own tables only — does **not** reopen `UNS_HISTORIAN`'s bronze decision ("keep everything, unlimited"), which stands as-is. Configurable via `.env`, not hardcoded |
| Module structure | New sibling folder `UNS_SILVER/`, own `docker-compose.yml`, own Postgres+TimescaleDB instance — independently deployable, one read-only cross-stack coupling (Historian's Postgres), matching the pattern `UNS_DASHBOARD` already established for its own historical backfill |

---

## Section 1 — Architecture

New sibling folder to `UNS_MANAGER/`, `UNS_HISTORIAN/`, `UNS_DASHBOARD/`: **`UNS_SILVER/`**, with its own `docker-compose.yml`, `.env.example`, and `scripts/{up,down,restart,logs,status}.sh` per `AGENTS.md`. Deployable and removable independently of the other stacks.

Two containers:

- **`uns_silver_postgres`** — `timescale/timescaledb:latest-pg16`. Dedicated instance, own named volume. No relation to `uns_historian_postgres` or `uns_dashboard_postgres`.
- **`uns_silver_normalizer`** — custom Python 3.12 background worker (`psycopg`, no MQTT client, no HTTP surface in this milestone). Its only external dependency is a read-only connection to `uns_historian_postgres`.

Two Docker networks:

- **`uns_net`** — the existing external network shared with `UNS_MANAGER`/`UNS_HISTORIAN`/`UNS_DASHBOARD`. Joined only by `uns_silver_normalizer`, to reach `uns_historian_postgres:5432` (already joined to `uns_net` since the Dashboard milestone).
- **`silver_net`** — internal bridge network, private to this stack. Connects `uns_silver_normalizer` ↔ `uns_silver_postgres`.

```
UNS_HISTORIAN                              UNS_SILVER
┌───────────────────────┐                  ┌──────────────────────────┐
│ uns_historian_postgres │◄──read-only──────┤ uns_silver_normalizer     │
│ (also joins uns_net)   │   (uns_net)      │  (uns_net + silver_net)   │
└───────────────────────┘                  └─────────────┬─────────────┘
                                                            │ silver_net
                                              ┌─────────────┴─────────────┐
                                              │ uns_silver_postgres        │
                                              │ (TimescaleDB)              │
                                              └───────────────────────────┘
```

### Two small, additive modifications to `UNS_HISTORIAN`

Documented and applied in `UNS_HISTORIAN`'s own repo area (same pattern as when `UNS_DASHBOARD` required `uns_historian_postgres` to join `uns_net`):

1. **Add `id BIGSERIAL PRIMARY KEY` to `mqtt_messages`.** The table currently has no monotonic ordering column — only `time`, which is not guaranteed unique (two different topics can easily share an identical timestamp at 1000+-topic scale). Without a monotonic `id`, a watermark-based consumer risks skipping or reprocessing rows. Purely additive; does not affect existing Historian behavior or queries.
2. **`NOTIFY silver_updates` after each flush** in the ingestor's flush loop, so the normalizer wakes immediately via `LISTEN` instead of waiting for its next poll cycle. Polling remains as a fallback (see Section 3) in case a notification is missed during a normalizer restart.

---

## Section 2 — Data Model (`uns_silver_postgres`)

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Versioned semantic catalog: physical signals AND KPI/analytics definitions
CREATE TABLE signal_catalog (
    id              BIGSERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,          -- ISA-95 node topic, any level, without suffix
    signal_key      TEXT NOT NULL,          -- flattened path: "Gen_RPM_Avg", "fleet_health_score.value"
    signal_type     TEXT NOT NULL,          -- 'raw' | 'kpi' | 'unknown'
    unit            TEXT,
    data_type       TEXT,
    range_min       NUMERIC,
    range_max       NUMERIC,
    thresholds      JSONB,                  -- warning_low/high, alarm_low/high, or arbitrary nested config
    description     TEXT,
    source_version  TEXT,                   -- _descriptive.schema_version or .analytical.version
    effective_since TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ,            -- NULL = currently active
    UNIQUE (topic, signal_key, effective_since)
);
CREATE INDEX idx_signal_catalog_active ON signal_catalog (topic, signal_key) WHERE effective_until IS NULL;

-- Normalized time-series readings (hypertable). Raw signals and KPI values share one table,
-- distinguished by signal_type (denormalized here to avoid a join on every agent query).
CREATE TABLE silver_readings (
    time          TIMESTAMPTZ NOT NULL,
    topic         TEXT NOT NULL,
    signal_key    TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    value_numeric NUMERIC,
    value_text    TEXT,                     -- non-numeric leaves, or JSON-encoded scalar arrays
    quality       TEXT NOT NULL DEFAULT 'good'
);
SELECT create_hypertable('silver_readings', 'time');
CREATE INDEX idx_silver_readings_lookup ON silver_readings (topic, signal_key, time DESC);

-- Event log: array-of-object occurrences (alarms, failure_events, ...) — one row per element,
-- full fidelity preserved, never forced into a scalar reading.
CREATE TABLE silver_events (
    time        TIMESTAMPTZ NOT NULL,
    topic       TEXT NOT NULL,
    event_key   TEXT NOT NULL,              -- the array's field name/path, e.g. "alarms"
    payload     JSONB NOT NULL,             -- the element object, verbatim
    signal_type TEXT NOT NULL DEFAULT 'unknown'
);
SELECT create_hypertable('silver_events', 'time');
CREATE INDEX idx_silver_events_lookup ON silver_events (topic, event_key, time DESC);

-- Latest value per signal — O(1) "current value" lookups
CREATE TABLE silver_latest_value (
    topic         TEXT NOT NULL,
    signal_key    TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    time          TIMESTAMPTZ NOT NULL,
    value_numeric NUMERIC,
    value_text    TEXT,
    PRIMARY KEY (topic, signal_key)
);

-- Normalizer watermark (single row)
CREATE TABLE silver_ingest_state (
    id                INT PRIMARY KEY DEFAULT 1,
    last_processed_id BIGINT NOT NULL DEFAULT 0
);

-- Continuous aggregates for fast historical queries at scale
CREATE MATERIALIZED VIEW silver_readings_1m
WITH (timescaledb.continuous) AS
SELECT topic, signal_key, signal_type,
       time_bucket('1 minute', time) AS bucket,
       avg(value_numeric) AS avg_value,
       min(value_numeric) AS min_value,
       max(value_numeric) AS max_value,
       count(*)           AS sample_count
FROM silver_readings
GROUP BY topic, signal_key, signal_type, bucket;

CREATE MATERIALIZED VIEW silver_readings_1h
WITH (timescaledb.continuous) AS
SELECT topic, signal_key, signal_type,
       time_bucket('1 hour', time) AS bucket,
       avg(value_numeric) AS avg_value,
       min(value_numeric) AS min_value,
       max(value_numeric) AS max_value,
       count(*)           AS sample_count
FROM silver_readings
GROUP BY topic, signal_key, signal_type, bucket;
```

`silver_readings` and `silver_events` carry TimescaleDB compression + retention policies, applied at startup from `.env` values (Section 4) rather than hardcoded in `init.sql`.

---

## Section 3 — Ingestion & Normalization Logic

Single Python process (`uns_silver_normalizer`), no web framework.

1. **Startup**: connect to `uns_silver_postgres` (schema via `init.sql`, mounted the same way `UNS_HISTORIAN` does it) and to `uns_historian_postgres` (read-only role). Load `silver_ingest_state.last_processed_id`.
2. **Wake-up**: `LISTEN silver_updates` on the Historian connection. On notification, or every `NORMALIZER_POLL_INTERVAL_SECONDS` (fallback, in case a notification was missed across a restart), query:
   ```sql
   SELECT id, time, topic, payload, raw_payload
   FROM mqtt_messages
   WHERE id > :last_processed_id
   ORDER BY id
   LIMIT :NORMALIZER_BATCH_SIZE
   ```
3. **Routing by topic suffix**: in every case below, `topic` as stored in `signal_catalog`/`silver_readings`/`silver_events`/`silver_latest_value` is the MQTT topic with its trailing suffix (`_descriptive`, `_informative`, `_analytical`) stripped — the same ISA-95 node topic underlies all three, and stripping the suffix is what lets a catalog entry loaded from `_descriptive` be found by a reading arriving on `_informative`/`_analytical` for that same node.
   - `_descriptive` → parse `signals` (raw physical signal definitions) and `analytical` (KPI/analytics definitions). For each signal/KPI key, compare against the currently-active `signal_catalog` row (by `topic`, `signal_key`, `effective_until IS NULL`): if any tracked field changed (unit/range/thresholds/description) or `source_version` differs, close the old row (`effective_until = message time`) and insert a new one (`effective_since = message time`). Unchanged signals are left as-is (no version noise).
   - Any other suffix (`_informative`, `_analytical`, or any future values-carrying topic) → **generic recursive flatten**, applied uniformly regardless of hierarchy level or publisher:
     - Scalar leaf (number/string/bool), at any nesting depth → one `silver_readings` row; `signal_key` is the dot-joined path (e.g. `fleet_health_score.value`, `status`, `active_alarms_count`).
     - Array of scalars → one `silver_readings` row; `value_text` = JSON-encoded array (it is a static list-shaped value, not a stream of occurrences).
     - Array of objects → one `silver_events` row per element; `event_key` = the array's field path; `payload` = the element, verbatim.
     - Recursion is capped (`MAX_FLATTEN_DEPTH`, `MAX_FLATTEN_KEYS_PER_MESSAGE`, both configurable) so a malformed or unexpectedly large payload can't explode into unbounded rows.
   - For every flattened `signal_key`, look up the active `signal_catalog` entry for `(topic, signal_key)`. If found, tag `signal_type` from the catalog (`raw`/`kpi`); if not found, tag `unknown` — never dropped.
   - Upsert `silver_latest_value` for every reading (not for events).
4. **Commit & watermark advance**: batch-insert readings/events/catalog changes and `silver_latest_value` upserts in one transaction per processed batch; update `silver_ingest_state.last_processed_id` to the highest `id` processed, committed atomically with the inserts (crash-safe: a restart simply resumes from the last committed watermark, no gap, no duplication).
5. **Logging**: structured logs for catalog version changes, unknown-signal occurrences (sampled, not per-row, to avoid log flooding at this scale), batch sizes, and errors (per `AGENTS.md`).

**Note on the future "declared value-shape" idea** (discussed and deferred): if a real case appears where the array-of-objects-is-always-an-event heuristic misclassifies something, `_descriptive.analytical` can later gain an optional `value_shape` map to override routing per key. Not built in this milestone — no observed case justifies it yet.

---

## Section 4 — Retention & Compression (Silver only)

Applies exclusively to `UNS_SILVER`'s own tables. Does not reopen or change `UNS_HISTORIAN`'s bronze retention decision (unlimited, unchanged).

Configured via `UNS_SILVER/.env`, applied by the normalizer at startup via `add_compression_policy`/`add_retention_policy` (idempotent — re-applied safely on every restart, updated if the env value changed):

| Variable | Default | Applies to |
|---|---|---|
| `RAW_COMPRESS_AFTER_DAYS` | `7` | `silver_readings`, `silver_events` — compress chunks older than this |
| `RAW_RETENTION_DAYS` | `90` | `silver_readings`, `silver_events` — drop chunks older than this |
| `AGG_1M_RETENTION_DAYS` | `0` (= keep forever) | `silver_readings_1m` |
| `AGG_1H_RETENTION_DAYS` | `0` (= keep forever) | `silver_readings_1h` |

---

## Section 5 — Deployment

- `UNS_SILVER/docker-compose.yml` — the two services from Section 1.
- `UNS_SILVER/.env.example`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `HISTORIAN_DATABASE_URL` (read-only role against `uns_historian_postgres`), `NORMALIZER_POLL_INTERVAL_SECONDS` (default `10`), `NORMALIZER_BATCH_SIZE` (default `2000`), `MAX_FLATTEN_DEPTH` (default `6`), `MAX_FLATTEN_KEYS_PER_MESSAGE` (default `500`), plus the four retention variables from Section 4.
- `UNS_SILVER/scripts/{up,down,restart,logs,status}.sh`, matching the existing pattern.
- `uns_silver_normalizer/Dockerfile` — `python:3.12-slim`, installs `psycopg[binary]`.
- README notes: `UNS_HISTORIAN` must be running first (`uns_net` external dependency, same convention already documented there); the two additive `UNS_HISTORIAN` schema/ingestor changes from Section 1 must be applied before first boot.
- Root `docker-compose.yml` gains a fourth `include:` entry for `UNS_SILVER/docker-compose.yml`.

---

## Section 6 — Testing

- **Unit tests** (no live Postgres required):
  - Recursive flattener: scalar leaf at various depths, array of scalars, array of objects, mixed/nested combinations (using the actual example payloads from this spec — generator signals, asset alarm status, fleet business targets, site regulatory compliance), depth/key-count cap enforcement.
  - Catalog versioning: new signal, unchanged definition (no new version row), changed unit/range/threshold (closes old row, opens new one), unknown signal_key (tagged `unknown`, not dropped).
  - Watermark logic: resume from `last_processed_id`, idempotent replay of an already-committed batch.
- **Integration tests**: seed `uns_historian_postgres` (test instance) with representative `_descriptive`, `_informative`, and `_analytical` rows (including the heterogeneous analytical shapes from this spec); run the normalizer; assert the expected `signal_catalog`, `silver_readings`, `silver_events`, and `silver_latest_value` rows.
- **Manual verification**: `docker compose up`, publish/update a real `_descriptive` and a few `_informative`/`_analytical` messages via `UNS_MANAGER`/Node-RED, confirm rows land correctly via a Postgres client against `uns_silver_postgres`.

---

## Explicitly deferred (future milestones)

- KPI/derived-metric **computation** (formulas, health-score evaluation) — remains the responsibility of an external service; Silver only ingests whatever it publishes.
- Declared `value_shape` override for the recursive flattener (Section 3 note) — add only if a real misclassification case appears.
- LLM/agent tool layer for querying Silver (current value, historical trend, catalog lookup) — the next sub-project, built on top of this spec.
- Chatbot-driven dashboard generation — depends on the agent tool layer above.
- Migrating `UNS_DASHBOARD`'s historical query path from `UNS_HISTORIAN` to `UNS_SILVER` (would benefit from continuous aggregates instead of ad hoc `time_bucket` over bronze JSONB) — a follow-on integration change to `UNS_DASHBOARD`, not part of this spec.
- Direct EMQX subscription for Silver (Option B from the architecture discussion) — revisit only if a genuine sub-second-freshness use case emerges; none identified so far.
- Authentication — none in v1, consistent with the other three stacks.
