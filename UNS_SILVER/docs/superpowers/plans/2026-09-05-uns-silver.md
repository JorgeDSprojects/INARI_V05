# UNS Silver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `UNS_SILVER/`, an independently-deployable module that normalizes `UNS_HISTORIAN`'s raw bronze JSONB into a versioned semantic catalog, typed per-signal time-series rows, an event log for array-shaped occurrences, a latest-value cache, and TimescaleDB retention/continuous aggregates — the foundation for a future LLM/agent query layer.

**Architecture:** Two new containers (`uns_silver_postgres`, `uns_silver_normalizer`) plus two small additive changes to `UNS_HISTORIAN` (a monotonic `id` column and a `NOTIFY` hook). The normalizer is a Python background worker with no MQTT client: it watches `uns_historian_postgres.mqtt_messages` via `LISTEN/NOTIFY` (polling as a fallback), routes each new row by topic suffix (`_descriptive` → catalog; `_informative`/`_analytical` → a generic recursive flattener), and writes to its own Postgres.

**Tech Stack:** Python 3.12, `psycopg` 3.x (`psycopg[binary]`), `pytest`, `timescale/timescaledb:latest-pg16`, `dpage/pgadmin4`, Docker Compose.

**Spec:** `UNS_SILVER/docs/superpowers/specs/2026-09-05-uns-silver-design.md`

## Global Constraints

- No MQTT client anywhere in `UNS_SILVER` — its only external dependency is a read-only-in-practice connection to `uns_historian_postgres`.
- KPI/derived-metric computation is out of scope — Silver only ingests and catalogs whatever a topic already carries.
- `topic` as stored in every Silver table has its trailing suffix (`_descriptive`/`_informative`/`_analytical`) stripped, so a catalog entry from `_descriptive` is found by a reading from `_informative`/`_analytical` on the same node.
- The recursive flattener is the only payload parser — no per-shape/per-level special-casing. Scalar leaf → `silver_readings` row; array of scalars → `silver_readings` row (JSON-encoded text); array of objects → one `silver_events` row per element. Capped by `MAX_FLATTEN_DEPTH` / `MAX_FLATTEN_KEYS_PER_MESSAGE`.
- A signal/KPI key with no matching catalog definition is tagged `signal_type='unknown'` and stored anyway — never dropped.
- The semantic catalog (`signal_catalog`) is versioned: a changed definition closes the old row (`effective_until`) and opens a new one (`effective_since`); an unchanged definition is left alone (no version noise).
- Retention/compression (`RAW_COMPRESS_AFTER_DAYS`, `RAW_RETENTION_DAYS`, `AGG_1M_RETENTION_DAYS`, `AGG_1H_RETENTION_DAYS`) applies only to `UNS_SILVER`'s own tables, configurable via `.env`, never hardcoded. `UNS_HISTORIAN`'s own "keep everything, unlimited" bronze decision is untouched.
- **Assumption (flag to the team publishing this data before go-live):** `_descriptive.analytical` is assumed to have the shape `{"version": ..., "kpis": {"<key>": {"unit", "data_type", "range_min", "range_max", "thresholds", "description"}, ...}}`. Raw physical signals keep their existing `_descriptive.signals` shape, with an optional new `thresholds` sub-key per signal (the old, now-retired `_analytical.thresholds` map's per-raw-signal entries move here). This wasn't pinned to a real example during design — only the container key name (`analytical`) was confirmed.
- `_descriptive.signals.<key>.default_chart` (dashboard chart-rendering hints) is explicitly **not** captured by Silver's catalog in v1 — it's UI metadata for `UNS_DASHBOARD`, not semantic meaning an agent needs.
- All code, comments, and commit messages in English (per repo `AGENTS.md`). Required `scripts/{up,down,restart,logs,status}.sh` per `AGENTS.md`.
- Service keys in `UNS_SILVER/docker-compose.yml` are prefixed (`silver_postgres`, `silver_pgadmin`, `silver_normalizer`), matching the convention `UNS_DASHBOARD` established to avoid the root compose's `include:` merging same-named services across stacks. Any hostname referenced from another service (env var, `servers.json`) uses the **container_name**, never the bare service key (confirmed against `UNS_HISTORIAN`'s current `pgadmin/servers.json`, which already follows this).
- Host ports: Postgres `5436` (after Manager `5433`, Historian `5434`, Dashboard `5435`), pgAdmin `5052` (after Historian's `5051`). No other host ports exposed.

---

## Task 1: `UNS_HISTORIAN` — monotonic `id` column + `NOTIFY` hook

**Files:**
- Modify: `UNS_HISTORIAN/postgres/init.sql`
- Create: `UNS_HISTORIAN/postgres/migrations/0001_add_silver_support.sql`
- Modify: `UNS_HISTORIAN/ingestor/app/db.py`
- Modify: `UNS_HISTORIAN/ingestor/app/main.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_db.py`

**Interfaces:**
- Produces: `mqtt_messages.id BIGSERIAL` column + `idx_mqtt_messages_id` index (fresh installs via `init.sql`; existing installs via the migration file). `app.db.notify_silver_updates(conn: psycopg.Connection) -> None`.

- [ ] **Step 1: Add the `id` column to the schema for fresh installs**

Edit `UNS_HISTORIAN/postgres/init.sql` — add `id BIGSERIAL` as the first column and a matching index. **Not** declared `PRIMARY KEY`: TimescaleDB requires a hypertable's unique/primary-key constraints to include the partitioning column (`time`), and a plain sequence + index is all a watermark cursor needs.

```sql
-- UNS_HISTORIAN/postgres/init.sql
-- UNS Historian schema — generic MQTT message capture.
-- See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 2.
-- `id` added for UNS_SILVER's watermark-based consumption — see
-- UNS_SILVER/docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 1.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS mqtt_messages (
    id           BIGSERIAL,
    time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,
    payload      JSONB,
    raw_payload  TEXT,
    qos          SMALLINT NOT NULL,
    retain       BOOLEAN NOT NULL
);

SELECT create_hypertable('mqtt_messages', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_mqtt_messages_topic_time ON mqtt_messages (topic, time DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_messages_id ON mqtt_messages (id);
```

- [ ] **Step 2: Write the migration for the already-initialized instance**

```sql
-- UNS_HISTORIAN/postgres/migrations/0001_add_silver_support.sql
-- Additive, idempotent. Apply to an already-running instance with:
--   docker compose exec -T historian_postgres psql -U historian -d uns_historian \
--     < postgres/migrations/0001_add_silver_support.sql
-- New instances get this from init.sql on first boot instead; running this
-- again there is a harmless no-op.
--
-- Not declared PRIMARY KEY: TimescaleDB requires a hypertable's unique/
-- primary-key constraints to include the partitioning column (`time`), and
-- a plain monotonic sequence + index is all a watermark cursor needs.
ALTER TABLE mqtt_messages ADD COLUMN IF NOT EXISTS id BIGSERIAL;
CREATE INDEX IF NOT EXISTS idx_mqtt_messages_id ON mqtt_messages (id);
```

- [ ] **Step 3: Write the failing test for the NOTIFY hook**

```python
# UNS_HISTORIAN/ingestor/tests/test_db.py — add to the existing file
def test_notify_silver_updates_is_received_by_a_listener(conn):
    listener = psycopg.connect(DATABASE_URL, autocommit=True)
    try:
        listener.execute("LISTEN silver_updates")
        notify_silver_updates(conn)
        received = list(listener.notifies(timeout=2))
        assert any(n.channel == "silver_updates" for n in received)
    finally:
        listener.close()
```

Add the import at the top of the file: `from app.db import insert_batch, load_last_values, notify_silver_updates`.

- [ ] **Step 4: Run test to verify it fails**

Run (with `UNS_HISTORIAN`'s Postgres up and `DATABASE_URL` exported): `pytest ingestor/tests/test_db.py::test_notify_silver_updates_is_received_by_a_listener -v`
Expected: FAIL with `ImportError: cannot import name 'notify_silver_updates'`

- [ ] **Step 5: Implement `notify_silver_updates`**

Add to `UNS_HISTORIAN/ingestor/app/db.py`:

```python
def notify_silver_updates(conn: psycopg.Connection) -> None:
    """Wake UNS_SILVER's normalizer immediately instead of making it wait for
    its next poll cycle. Safe to call even if nothing is listening. Commits
    (NOTIFY only takes effect on commit), independent of the caller's own
    transaction boundaries."""
    conn.execute("NOTIFY silver_updates")
    conn.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest ingestor/tests/test_db.py::test_notify_silver_updates_is_received_by_a_listener -v`
Expected: PASS

- [ ] **Step 7: Call it from the flush loop**

In `UNS_HISTORIAN/ingestor/app/main.py`:
- Update the import: `from app.db import insert_batch, load_last_values, notify_silver_updates`
- In `_flush_loop`, right after the existing `logger.info("Flushed %d row(s)", inserted)` line (inside the `try` block that calls `insert_batch`), add:

```python
                    notify_silver_updates(conn)
```

- [ ] **Step 8: Run the full Historian test suite**

Run: `pytest ingestor/tests/ -v`
Expected: PASS (all tests, including the new one)

- [ ] **Step 9: Apply the migration to the running instance and commit**

```bash
cd UNS_HISTORIAN
docker compose exec -T historian_postgres psql -U historian -d uns_historian < postgres/migrations/0001_add_silver_support.sql
git add postgres/init.sql postgres/migrations/0001_add_silver_support.sql ingestor/app/db.py ingestor/app/main.py ingestor/tests/test_db.py
git commit -m "feat(uns-historian): add id column and NOTIFY hook for UNS_SILVER"
```

---

## Task 2: `UNS_SILVER` scaffolding — schema, compose, scripts

**Files:**
- Create: `UNS_SILVER/postgres/init.sql`
- Create: `UNS_SILVER/pgadmin/servers.json`
- Create: `UNS_SILVER/docker-compose.yml`
- Create: `UNS_SILVER/.env.example`
- Create: `UNS_SILVER/.gitignore`
- Create: `UNS_SILVER/scripts/up.sh`, `down.sh`, `restart.sh`, `logs.sh`, `status.sh`

**Interfaces:**
- Produces: tables `signal_catalog`, `silver_readings` (hypertable), `silver_events` (hypertable), `silver_latest_value`, `silver_ingest_state`, and continuous aggregates `silver_readings_1m`/`silver_readings_1h`, all in `uns_silver_postgres`, reachable at container name `uns_silver_postgres:5432`.

- [ ] **Step 1: Write the schema**

```sql
-- UNS_SILVER/postgres/init.sql
-- UNS Silver schema — versioned semantic catalog + normalized readings/events.
-- See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 2.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS signal_catalog (
    id              BIGSERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    signal_key      TEXT NOT NULL,
    signal_type     TEXT NOT NULL,
    unit            TEXT,
    data_type       TEXT,
    range_min       NUMERIC,
    range_max       NUMERIC,
    thresholds      JSONB,
    description     TEXT,
    source_version  TEXT,
    effective_since TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ,
    UNIQUE (topic, signal_key, effective_since)
);
CREATE INDEX IF NOT EXISTS idx_signal_catalog_active ON signal_catalog (topic, signal_key) WHERE effective_until IS NULL;

CREATE TABLE IF NOT EXISTS silver_readings (
    time          TIMESTAMPTZ NOT NULL,
    topic         TEXT NOT NULL,
    signal_key    TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    value_numeric NUMERIC,
    value_text    TEXT,
    quality       TEXT NOT NULL DEFAULT 'good'
);
SELECT create_hypertable('silver_readings', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_silver_readings_lookup ON silver_readings (topic, signal_key, time DESC);

CREATE TABLE IF NOT EXISTS silver_events (
    time        TIMESTAMPTZ NOT NULL,
    topic       TEXT NOT NULL,
    event_key   TEXT NOT NULL,
    payload     JSONB NOT NULL,
    signal_type TEXT NOT NULL DEFAULT 'unknown'
);
SELECT create_hypertable('silver_events', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_silver_events_lookup ON silver_events (topic, event_key, time DESC);

CREATE TABLE IF NOT EXISTS silver_latest_value (
    topic         TEXT NOT NULL,
    signal_key    TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    time          TIMESTAMPTZ NOT NULL,
    value_numeric NUMERIC,
    value_text    TEXT,
    PRIMARY KEY (topic, signal_key)
);

CREATE TABLE IF NOT EXISTS silver_ingest_state (
    id                INT PRIMARY KEY DEFAULT 1,
    last_processed_id BIGINT NOT NULL DEFAULT 0
);
INSERT INTO silver_ingest_state (id, last_processed_id) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver_readings_1m
WITH (timescaledb.continuous) AS
SELECT topic, signal_key, signal_type,
       time_bucket('1 minute', time) AS bucket,
       avg(value_numeric) AS avg_value,
       min(value_numeric) AS min_value,
       max(value_numeric) AS max_value,
       count(*)           AS sample_count
FROM silver_readings
GROUP BY topic, signal_key, signal_type, bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver_readings_1h
WITH (timescaledb.continuous) AS
SELECT topic, signal_key, signal_type,
       time_bucket('1 hour', time) AS bucket,
       avg(value_numeric) AS avg_value,
       min(value_numeric) AS min_value,
       max(value_numeric) AS max_value,
       count(*)           AS sample_count
FROM silver_readings
GROUP BY topic, signal_key, signal_type, bucket
WITH NO DATA;
```

- [ ] **Step 2: Write the pgAdmin pre-registered connection**

```json
{
  "Servers": {
    "1": {
      "Name": "UNS Silver",
      "Group": "Servers",
      "Host": "uns_silver_postgres",
      "Port": 5432,
      "MaintenanceDB": "uns_silver",
      "Username": "silver",
      "SSLMode": "prefer"
    }
  }
}
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  silver_postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: uns_silver_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-silver}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-silverpassword}
      POSTGRES_DB: ${POSTGRES_DB:-uns_silver}
    volumes:
      - silver_postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "${POSTGRES_PORT:-5436}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-silver} -d ${POSTGRES_DB:-uns_silver}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - silver_net

  silver_pgadmin:
    image: dpage/pgadmin4:latest
    container_name: uns_silver_pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: ${PGADMIN_DEFAULT_EMAIL:-admin@uns-silver.local}
      PGADMIN_DEFAULT_PASSWORD: ${PGADMIN_DEFAULT_PASSWORD:-pgadminpassword}
      PGADMIN_CONFIG_SERVER_MODE: "False"
    volumes:
      - silver_pgadmin_data:/var/lib/pgadmin
      - ./pgadmin/servers.json:/pgadmin4/servers.json:ro
    ports:
      - "${PGADMIN_PORT:-5052}:80"
    depends_on:
      silver_postgres:
        condition: service_healthy
    networks:
      - silver_net
    restart: unless-stopped

  silver_normalizer:
    build:
      context: ./normalizer
      dockerfile: Dockerfile
    container_name: uns_silver_normalizer
    init: true
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql://${POSTGRES_USER:-silver}:${POSTGRES_PASSWORD:-silverpassword}@uns_silver_postgres:5432/${POSTGRES_DB:-uns_silver}}
      HISTORIAN_DATABASE_URL: ${HISTORIAN_DATABASE_URL:-postgresql://historian:historianpassword@uns_historian_postgres:5432/uns_historian}
      NORMALIZER_POLL_INTERVAL_SECONDS: ${NORMALIZER_POLL_INTERVAL_SECONDS:-10}
      NORMALIZER_BATCH_SIZE: ${NORMALIZER_BATCH_SIZE:-2000}
      MAX_FLATTEN_DEPTH: ${MAX_FLATTEN_DEPTH:-6}
      MAX_FLATTEN_KEYS_PER_MESSAGE: ${MAX_FLATTEN_KEYS_PER_MESSAGE:-500}
      RAW_COMPRESS_AFTER_DAYS: ${RAW_COMPRESS_AFTER_DAYS:-7}
      RAW_RETENTION_DAYS: ${RAW_RETENTION_DAYS:-90}
      AGG_1M_RETENTION_DAYS: ${AGG_1M_RETENTION_DAYS:-0}
      AGG_1H_RETENTION_DAYS: ${AGG_1H_RETENTION_DAYS:-0}
    depends_on:
      silver_postgres:
        condition: service_healthy
    networks:
      - silver_net
      - uns_manager_net
    restart: unless-stopped

volumes:
  silver_postgres_data:
    name: uns_silver_silver_postgres_data
  silver_pgadmin_data:
    name: uns_silver_silver_pgadmin_data

networks:
  silver_net:
    driver: bridge
    name: uns_silver_silver_net
  uns_manager_net:
    external: true
    name: ${UNS_MANAGER_NETWORK_NAME:-uns_manager_uns_net}
```

- [ ] **Step 4: Write `.env.example`**

```
# PostgreSQL (TimescaleDB)
POSTGRES_USER=silver
POSTGRES_PASSWORD=silverpassword
POSTGRES_DB=uns_silver
POSTGRES_PORT=5436

# pgAdmin
PGADMIN_DEFAULT_EMAIL=admin@uns-silver.local
PGADMIN_DEFAULT_PASSWORD=pgadminpassword
PGADMIN_PORT=5052

DATABASE_URL=postgresql://silver:silverpassword@uns_silver_postgres:5432/uns_silver

# UNS_HISTORIAN's Postgres (must already be running). Credentials match
# UNS_HISTORIAN's own defaults; override here if that stack's .env differs.
HISTORIAN_DATABASE_URL=postgresql://historian:historianpassword@uns_historian_postgres:5432/uns_historian

# Normalizer behavior
NORMALIZER_POLL_INTERVAL_SECONDS=10
NORMALIZER_BATCH_SIZE=2000
MAX_FLATTEN_DEPTH=6
MAX_FLATTEN_KEYS_PER_MESSAGE=500

# Retention/compression — applies only to UNS_SILVER's own tables
RAW_COMPRESS_AFTER_DAYS=7
RAW_RETENTION_DAYS=90
AGG_1M_RETENTION_DAYS=0
AGG_1H_RETENTION_DAYS=0

# Docker network shared with UNS_MANAGER (same variable UNS_HISTORIAN and
# UNS_DASHBOARD use). Verify with: docker network ls | grep uns_net
UNS_MANAGER_NETWORK_NAME=uns_manager_uns_net
```

- [ ] **Step 5: Write `.gitignore`**

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 6: Write the operational scripts**

```bash
# UNS_SILVER/scripts/up.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build
echo "UNS Silver is starting. Use scripts/status.sh to check container health."
```

```bash
# UNS_SILVER/scripts/down.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
```

```bash
# UNS_SILVER/scripts/restart.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
service="${1:-}"
if [ -n "$service" ]; then
  docker compose restart "$service"
else
  docker compose down
  docker compose up -d --build
fi
```

```bash
# UNS_SILVER/scripts/logs.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
service="${1:-}"
if [ -n "$service" ]; then
  docker compose logs -f "$service"
else
  docker compose logs -f
fi
```

```bash
# UNS_SILVER/scripts/status.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
```

- [ ] **Step 7: Make scripts executable and commit**

```bash
cd UNS_SILVER
chmod +x scripts/*.sh
git add postgres/init.sql pgadmin/servers.json docker-compose.yml .env.example .gitignore scripts/
git commit -m "feat(uns-silver): scaffold schema, compose, and operational scripts"
```

---

## Task 3: `config.py`

**Files:**
- Create: `UNS_SILVER/normalizer/requirements.txt`
- Create: `UNS_SILVER/normalizer/app/__init__.py`
- Create: `UNS_SILVER/normalizer/app/config.py`
- Test: `UNS_SILVER/normalizer/tests/__init__.py`
- Test: `UNS_SILVER/normalizer/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` dataclass (fields: `database_url`, `historian_database_url`, `poll_interval_seconds`, `batch_size`, `max_flatten_depth`, `max_flatten_keys`, `raw_compress_after_days`, `raw_retention_days`, `agg_1m_retention_days`, `agg_1h_retention_days`) and `load_settings(env: dict[str, str] | None = None) -> Settings`.

- [ ] **Step 1: Write `requirements.txt` and package init files**

```
psycopg[binary]==3.2.3
pytest==8.3.3
```

```python
# UNS_SILVER/normalizer/app/__init__.py
```

```python
# UNS_SILVER/normalizer/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# UNS_SILVER/normalizer/tests/test_config.py
from app.config import load_settings


def test_defaults_when_env_is_empty():
    settings = load_settings({})
    assert settings.database_url == "postgresql://silver:silverpassword@uns_silver_postgres:5432/uns_silver"
    assert settings.historian_database_url == "postgresql://historian:historianpassword@uns_historian_postgres:5432/uns_historian"
    assert settings.poll_interval_seconds == 10.0
    assert settings.batch_size == 2000
    assert settings.max_flatten_depth == 6
    assert settings.max_flatten_keys == 500
    assert settings.raw_compress_after_days == 7
    assert settings.raw_retention_days == 90
    assert settings.agg_1m_retention_days == 0
    assert settings.agg_1h_retention_days == 0


def test_env_overrides_defaults():
    settings = load_settings({"NORMALIZER_BATCH_SIZE": "50", "RAW_RETENTION_DAYS": "30"})
    assert settings.batch_size == 50
    assert settings.raw_retention_days == 30
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `UNS_SILVER/normalizer/`): `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 4: Implement `config.py`**

```python
# UNS_SILVER/normalizer/app/config.py
"""Environment-variable configuration for the Silver normalizer."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    historian_database_url: str
    poll_interval_seconds: float
    batch_size: int
    max_flatten_depth: int
    max_flatten_keys: int
    raw_compress_after_days: int
    raw_retention_days: int
    agg_1m_retention_days: int
    agg_1h_retention_days: int


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        database_url=e.get(
            "DATABASE_URL", "postgresql://silver:silverpassword@uns_silver_postgres:5432/uns_silver"
        ),
        historian_database_url=e.get(
            "HISTORIAN_DATABASE_URL",
            "postgresql://historian:historianpassword@uns_historian_postgres:5432/uns_historian",
        ),
        poll_interval_seconds=float(e.get("NORMALIZER_POLL_INTERVAL_SECONDS", "10")),
        batch_size=int(e.get("NORMALIZER_BATCH_SIZE", "2000")),
        max_flatten_depth=int(e.get("MAX_FLATTEN_DEPTH", "6")),
        max_flatten_keys=int(e.get("MAX_FLATTEN_KEYS_PER_MESSAGE", "500")),
        raw_compress_after_days=int(e.get("RAW_COMPRESS_AFTER_DAYS", "7")),
        raw_retention_days=int(e.get("RAW_RETENTION_DAYS", "90")),
        agg_1m_retention_days=int(e.get("AGG_1M_RETENTION_DAYS", "0")),
        agg_1h_retention_days=int(e.get("AGG_1H_RETENTION_DAYS", "0")),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd UNS_SILVER/normalizer
git add requirements.txt app/__init__.py app/config.py tests/__init__.py tests/test_config.py
git commit -m "feat(uns-silver): add normalizer settings module"
```

---

## Task 4: `topics.py`

**Files:**
- Create: `UNS_SILVER/normalizer/app/topics.py`
- Test: `UNS_SILVER/normalizer/tests/test_topics.py`

**Interfaces:**
- Produces: `classify_topic(topic: str) -> tuple[str, str]` returning `(base_topic, suffix)` where `suffix` is one of `"descriptive"`, `"informative"`, `"analytical"`, `"other"`.

- [ ] **Step 1: Write the failing test**

```python
# UNS_SILVER/normalizer/tests/test_topics.py
from app.topics import classify_topic


def test_descriptive_suffix_is_stripped():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_descriptive")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR"
    assert suffix == "descriptive"


def test_informative_suffix_is_stripped():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_informative")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR"
    assert suffix == "informative"


def test_analytical_suffix_is_stripped():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_analytical")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR"
    assert suffix == "analytical"


def test_unrecognized_suffix_is_other_and_unchanged():
    base, suffix = classify_topic("uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_lifecycle")
    assert base == "uns/v1/ACME/SITE/AREA/L1/T01/GENERATOR/_lifecycle"
    assert suffix == "other"


def test_suffix_can_apply_at_any_hierarchy_level():
    base, suffix = classify_topic("uns/v1/ACME/SITE/_analytical")
    assert base == "uns/v1/ACME/SITE"
    assert suffix == "analytical"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_topics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.topics'`

- [ ] **Step 3: Implement `topics.py`**

```python
# UNS_SILVER/normalizer/app/topics.py
"""Classify an MQTT topic by its UNS suffix and strip it to the base
ISA-95 node topic that catalog entries and readings/events are keyed on.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3.
"""
from __future__ import annotations

_SUFFIXES = {
    "/_descriptive": "descriptive",
    "/_informative": "informative",
    "/_analytical": "analytical",
}


def classify_topic(topic: str) -> tuple[str, str]:
    for suffix, name in _SUFFIXES.items():
        if topic.endswith(suffix):
            return topic[: -len(suffix)], name
    return topic, "other"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_topics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/topics.py tests/test_topics.py
git commit -m "feat(uns-silver): add topic suffix classification"
```

---

## Task 5: `flatten.py`

**Files:**
- Create: `UNS_SILVER/normalizer/app/flatten.py`
- Test: `UNS_SILVER/normalizer/tests/test_flatten.py`

**Interfaces:**
- Produces: `FlatValue(path: str, value_numeric: float | None, value_text: str | None)`, `FlatEvent(event_key: str, payload: dict)`, `FlattenResult(values: list[FlatValue], events: list[FlatEvent], truncated: bool)`, `flatten_payload(payload: Any, max_depth: int, max_keys: int) -> FlattenResult`.

- [ ] **Step 1: Write the failing tests**

```python
# UNS_SILVER/normalizer/tests/test_flatten.py
from app.flatten import FlatEvent, FlatValue, flatten_payload


def test_top_level_scalars_become_values():
    result = flatten_payload({"Gen_RPM_Avg": 1249.0, "status": "WARNING"}, max_depth=6, max_keys=500)
    assert FlatValue(path="Gen_RPM_Avg", value_numeric=1249.0, value_text=None) in result.values
    assert FlatValue(path="status", value_numeric=None, value_text="WARNING") in result.values
    assert result.events == []
    assert result.truncated is False


def test_top_level_timestamp_key_is_skipped():
    result = flatten_payload({"timestamp": "2026-09-05T13:52:54.269Z", "status": "OK"}, max_depth=6, max_keys=500)
    paths = [v.path for v in result.values]
    assert "timestamp" not in paths
    assert "status" in paths


def test_nested_scalar_becomes_dot_path_value():
    result = flatten_payload({"fleet_health_score": {"value": 0.88, "confidence": 0.85}}, max_depth=6, max_keys=500)
    assert FlatValue(path="fleet_health_score.value", value_numeric=0.88, value_text=None) in result.values
    assert FlatValue(path="fleet_health_score.confidence", value_numeric=0.85, value_text=None) in result.values


def test_array_of_scalars_becomes_one_json_text_value():
    result = flatten_payload({"escalation_timeout_minutes": [15, 60, 240]}, max_depth=6, max_keys=500)
    assert result.values == [FlatValue(path="escalation_timeout_minutes", value_numeric=None, value_text="[15, 60, 240]")]
    assert result.events == []


def test_array_of_objects_becomes_one_event_per_element():
    payload = {
        "status": "WARNING",
        "alarms": [
            {"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4, "threshold_violated": 1400},
        ],
    }
    result = flatten_payload(payload, max_depth=6, max_keys=500)
    assert result.events == [
        FlatEvent(
            event_key="alarms",
            payload={"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4, "threshold_violated": 1400},
        )
    ]
    assert FlatValue(path="status", value_numeric=None, value_text="WARNING") in result.values


def test_boolean_is_stored_as_text():
    result = flatten_payload({"has_slip_ring": True}, max_depth=6, max_keys=500)
    assert result.values == [FlatValue(path="has_slip_ring", value_numeric=None, value_text="True")]


def test_null_is_stored_as_value_with_no_numeric_or_text():
    result = flatten_payload({"note": None}, max_depth=6, max_keys=500)
    assert result.values == [FlatValue(path="note", value_numeric=None, value_text=None)]


def test_depth_cap_truncates_and_flags():
    deeply_nested = {"a": {"b": {"c": {"d": 1}}}}
    result = flatten_payload(deeply_nested, max_depth=2, max_keys=500)
    assert result.truncated is True
    assert result.values == []


def test_key_count_cap_truncates_and_flags():
    payload = {f"key_{i}": i for i in range(10)}
    result = flatten_payload(payload, max_depth=6, max_keys=5)
    assert len(result.values) == 5
    assert result.truncated is True


def test_non_dict_payload_returns_empty_result():
    result = flatten_payload("not a dict", max_depth=6, max_keys=500)
    assert result.values == []
    assert result.events == []
    assert result.truncated is False


def test_empty_array_produces_nothing():
    result = flatten_payload({"failure_events": []}, max_depth=6, max_keys=500)
    assert result.values == []
    assert result.events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_flatten.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.flatten'`

- [ ] **Step 3: Implement `flatten.py`**

```python
# UNS_SILVER/normalizer/app/flatten.py
"""Generic recursive flattener for `_informative`/`_analytical` value
payloads. Deliberately not a per-shape parser: it works uniformly across
every ISA-95 hierarchy level and every publisher, because analytical
payloads are not a stable project-wide schema (asset-level alarm status,
fleet-level business targets, site-level regulatory compliance all differ).

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3,
second bullet ("generic recursive flatten").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# The message envelope's own event time is already captured by the bronze
# row's `time` column (reused verbatim for every row Silver produces from
# that message) — flattening it again as a signal would just be noise.
_ENVELOPE_KEYS_SKIPPED_AT_ROOT = {"timestamp"}


@dataclass
class FlatValue:
    path: str
    value_numeric: float | None
    value_text: str | None


@dataclass
class FlatEvent:
    event_key: str
    payload: dict


@dataclass
class FlattenResult:
    values: list[FlatValue] = field(default_factory=list)
    events: list[FlatEvent] = field(default_factory=list)
    truncated: bool = False


def flatten_payload(payload: Any, max_depth: int, max_keys: int) -> FlattenResult:
    result = FlattenResult()
    if not isinstance(payload, dict):
        return result
    _walk(payload, path=None, depth=0, max_depth=max_depth, max_keys=max_keys, result=result, is_root=True)
    return result


def _walk(
    node: Any,
    path: str | None,
    depth: int,
    max_depth: int,
    max_keys: int,
    result: FlattenResult,
    is_root: bool = False,
) -> None:
    if len(result.values) + len(result.events) >= max_keys:
        result.truncated = True
        return

    if isinstance(node, dict):
        if depth >= max_depth:
            result.truncated = True
            return
        for key, child in node.items():
            if is_root and key in _ENVELOPE_KEYS_SKIPPED_AT_ROOT:
                continue
            child_path = key if path is None else f"{path}.{key}"
            _walk(child, child_path, depth + 1, max_depth, max_keys, result)
        return

    if isinstance(node, list):
        if path is None:
            return  # a bare top-level array has no key to attach a path to
        if node and all(isinstance(item, dict) for item in node):
            for item in node:
                result.events.append(FlatEvent(event_key=path, payload=item))
        elif node:
            result.values.append(FlatValue(path=path, value_numeric=None, value_text=json.dumps(node)))
        return

    if path is None:
        return  # a bare top-level scalar has no key (shouldn't occur for a JSON object payload)

    if isinstance(node, bool):
        result.values.append(FlatValue(path=path, value_numeric=None, value_text=str(node)))
    elif isinstance(node, (int, float)):
        result.values.append(FlatValue(path=path, value_numeric=float(node), value_text=None))
    elif node is None:
        result.values.append(FlatValue(path=path, value_numeric=None, value_text=None))
    else:
        result.values.append(FlatValue(path=path, value_numeric=None, value_text=str(node)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_flatten.py -v`
Expected: PASS (all 11 tests)

- [ ] **Step 5: Commit**

```bash
git add app/flatten.py tests/test_flatten.py
git commit -m "feat(uns-silver): add generic recursive payload flattener"
```

---

## Task 6: `catalog.py`

**Files:**
- Create: `UNS_SILVER/normalizer/app/catalog.py`
- Test: `UNS_SILVER/normalizer/tests/test_catalog.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SignalDefinition(signal_key, signal_type, unit=None, data_type=None, range_min=None, range_max=None, thresholds=None, description=None, source_version=None)`, `extract_definitions(descriptive_payload: dict) -> list[SignalDefinition]`, `diff_definitions(active: dict[str, SignalDefinition], incoming: list[SignalDefinition]) -> list[SignalDefinition]`.

- [ ] **Step 1: Write the failing tests**

```python
# UNS_SILVER/normalizer/tests/test_catalog.py
from app.catalog import SignalDefinition, diff_definitions, extract_definitions


def test_extract_raw_signal_definitions():
    payload = {
        "schema_version": "1.0.0",
        "signals": {
            "Gen_RPM_Avg": {
                "unit": "RPM", "data_type": "float", "range_min": 0, "range_max": 1700,
                "thresholds": {"warning_high": 1400, "alarm_high": 1500},
            },
        },
    }
    definitions = extract_definitions(payload)
    assert definitions == [
        SignalDefinition(
            signal_key="Gen_RPM_Avg", signal_type="raw", unit="RPM", data_type="float",
            range_min=0, range_max=1700, thresholds={"warning_high": 1400, "alarm_high": 1500},
            description=None, source_version="1.0.0",
        )
    ]


def test_extract_kpi_definitions():
    payload = {
        "analytical": {
            "version": 2,
            "kpis": {
                "phase_imbalance_max_delta_c": {
                    "unit": "°C", "thresholds": {"warning": 5, "alarm": 10},
                    "description": "Max difference between any two phase temperatures",
                },
            },
        },
    }
    definitions = extract_definitions(payload)
    assert definitions == [
        SignalDefinition(
            signal_key="phase_imbalance_max_delta_c", signal_type="kpi", unit="°C", data_type=None,
            range_min=None, range_max=None, thresholds={"warning": 5, "alarm": 10},
            description="Max difference between any two phase temperatures", source_version="2",
        )
    ]


def test_missing_sections_yield_no_definitions():
    assert extract_definitions({"schema_version": "1.0.0"}) == []


def test_malformed_signal_entry_is_skipped_not_raised():
    payload = {"signals": {"Gen_RPM_Avg": "not an object"}}
    assert extract_definitions(payload) == []


def test_diff_flags_brand_new_signal():
    incoming = [SignalDefinition(signal_key="a", signal_type="raw", unit="RPM")]
    assert diff_definitions({}, incoming) == incoming


def test_diff_ignores_unchanged_signal():
    definition = SignalDefinition(signal_key="a", signal_type="raw", unit="RPM")
    assert diff_definitions({"a": definition}, [definition]) == []


def test_diff_flags_changed_threshold():
    old = SignalDefinition(signal_key="a", signal_type="raw", unit="RPM", thresholds={"warning_high": 1400})
    new = SignalDefinition(signal_key="a", signal_type="raw", unit="RPM", thresholds={"warning_high": 1450})
    assert diff_definitions({"a": old}, [new]) == [new]


def test_diff_flags_changed_range():
    old = SignalDefinition(signal_key="a", signal_type="raw", range_min=0, range_max=1700)
    new = SignalDefinition(signal_key="a", signal_type="raw", range_min=0, range_max=1800)
    assert diff_definitions({"a": old}, [new]) == [new]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.catalog'`

- [ ] **Step 3: Implement `catalog.py`**

```python
# UNS_SILVER/normalizer/app/catalog.py
"""Parse `_descriptive` payloads into flat signal/KPI definitions, and diff
them against the currently active catalog to decide what needs a new
versioned row.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Key Decisions
("Topic structure") and the Global Constraints assumption about
`_descriptive.analytical`'s shape:

    "analytical": {
        "version": 2,
        "kpis": {
            "health_score": {"unit": null, "data_type": "float", "description": "...", "thresholds": {...}},
            ...
        }
    }

Raw physical signals keep their existing `signals` shape, with an optional
new `thresholds` sub-key per signal (previously lived in the now-retired
`_analytical.thresholds` map).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SignalDefinition:
    signal_key: str
    signal_type: str  # 'raw' | 'kpi'
    unit: str | None = None
    data_type: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    thresholds: dict | None = None
    description: str | None = None
    source_version: str | None = None


_COMPARABLE_FIELDS = (
    "signal_type", "unit", "data_type", "range_min", "range_max",
    "thresholds", "description", "source_version",
)


def extract_definitions(descriptive_payload: dict[str, Any]) -> list[SignalDefinition]:
    """Never raises on a malformed/missing section — returns whatever can be
    parsed, skipping entries that aren't the expected shape."""
    definitions: list[SignalDefinition] = []
    schema_version = descriptive_payload.get("schema_version")

    signals = descriptive_payload.get("signals")
    if isinstance(signals, dict):
        for key, spec in signals.items():
            if not isinstance(spec, dict):
                continue
            definitions.append(
                SignalDefinition(
                    signal_key=key,
                    signal_type="raw",
                    unit=spec.get("unit"),
                    data_type=spec.get("data_type"),
                    range_min=spec.get("range_min"),
                    range_max=spec.get("range_max"),
                    thresholds=spec.get("thresholds"),
                    description=spec.get("description"),
                    source_version=schema_version,
                )
            )

    analytical = descriptive_payload.get("analytical")
    if isinstance(analytical, dict):
        analytical_version = analytical.get("version")
        kpis = analytical.get("kpis")
        if isinstance(kpis, dict):
            for key, spec in kpis.items():
                if not isinstance(spec, dict):
                    continue
                definitions.append(
                    SignalDefinition(
                        signal_key=key,
                        signal_type="kpi",
                        unit=spec.get("unit"),
                        data_type=spec.get("data_type"),
                        range_min=spec.get("range_min"),
                        range_max=spec.get("range_max"),
                        thresholds=spec.get("thresholds"),
                        description=spec.get("description"),
                        source_version=str(analytical_version) if analytical_version is not None else None,
                    )
                )

    return definitions


def diff_definitions(
    active: dict[str, SignalDefinition], incoming: list[SignalDefinition]
) -> list[SignalDefinition]:
    """Return the subset of `incoming` that differs from (or has no) active
    definition for that signal_key — the ones that need a new versioned
    catalog row."""
    changed = []
    for definition in incoming:
        current = active.get(definition.signal_key)
        if current is None or _differs(current, definition):
            changed.append(definition)
    return changed


def _differs(current: SignalDefinition, incoming: SignalDefinition) -> bool:
    return any(getattr(current, f) != getattr(incoming, f) for f in _COMPARABLE_FIELDS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_catalog.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/catalog.py tests/test_catalog.py
git commit -m "feat(uns-silver): add descriptive-payload definition parsing and diffing"
```

---

## Task 7: `db.py`

**Files:**
- Create: `UNS_SILVER/normalizer/app/db.py`
- Test: `UNS_SILVER/normalizer/tests/test_db.py`

**Interfaces:**
- Consumes: `app.catalog.SignalDefinition` (Task 6).
- Produces: `BronzeRow(id, time, topic, payload)`; `fetch_watermark(conn) -> int`; `save_watermark(conn, last_id: int) -> None`; `fetch_new_bronze_rows(historian_conn, after_id: int, limit: int) -> list[BronzeRow]`; `fetch_active_definitions(conn, topic: str) -> dict[str, SignalDefinition]`; `apply_catalog_changes(conn, topic: str, changed: list[SignalDefinition], observed_at: datetime) -> None`; `insert_readings(conn, rows: Iterable[tuple]) -> int` (row = `(time, topic, signal_key, signal_type, value_numeric, value_text)`); `insert_events(conn, rows: Iterable[tuple]) -> int` (row = `(time, topic, event_key, payload, signal_type)`); `upsert_latest_values(conn, rows: Iterable[tuple]) -> None` (same row shape as `insert_readings`).

**Test setup note:** integration tests need both a Silver-shaped schema and a bronze-shaped `mqtt_messages` table. To avoid requiring the full `UNS_HISTORIAN` stack, tests create a throwaway `mqtt_messages` table (same shape Historian uses) in the same test Postgres instance that already has Silver's schema applied — this tests the SQL logic in `db.py`, not the two-database network topology (that's covered by Task 2's compose file + Task 9's manual verification).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_SILVER/normalizer/tests/test_db.py
import os
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.catalog import SignalDefinition
from app.db import (
    BronzeRow,
    apply_catalog_changes,
    fetch_active_definitions,
    fetch_new_bronze_rows,
    fetch_watermark,
    insert_events,
    insert_readings,
    save_watermark,
    upsert_latest_values,
)

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    connection.execute("DELETE FROM signal_catalog WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_readings WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_events WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_latest_value WHERE topic LIKE 'pytest/%'")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mqtt_messages (
            id BIGSERIAL, time TIMESTAMPTZ NOT NULL, topic TEXT NOT NULL, payload JSONB
        )
        """
    )
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    yield connection
    connection.rollback()
    connection.execute("DELETE FROM signal_catalog WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_readings WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_events WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_latest_value WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    connection.close()


def test_watermark_defaults_to_zero_then_roundtrips(conn):
    save_watermark(conn, 0)  # reset in case a prior failed run left state
    assert fetch_watermark(conn) == 0
    save_watermark(conn, 42)
    assert fetch_watermark(conn) == 42


def test_fetch_new_bronze_rows_respects_watermark_and_limit(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO mqtt_messages (time, topic, payload) VALUES (%s, %s, %s)",
            [(now, f"pytest/t{i}", Jsonb({"v": i})) for i in range(3)],
        )
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM mqtt_messages WHERE topic = 'pytest/t0'")
        first_id = cur.fetchone()[0]

    rows = fetch_new_bronze_rows(conn, after_id=first_id, limit=10)
    assert [r.topic for r in rows] == ["pytest/t1", "pytest/t2"]
    assert all(isinstance(r, BronzeRow) for r in rows)

    limited = fetch_new_bronze_rows(conn, after_id=first_id, limit=1)
    assert len(limited) == 1


def test_apply_and_fetch_active_definitions(conn):
    observed_at = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    definition = SignalDefinition(signal_key="Gen_RPM_Avg", signal_type="raw", unit="RPM", range_min=0, range_max=1700)
    apply_catalog_changes(conn, "pytest/T01/GENERATOR", [definition], observed_at)
    conn.commit()

    active = fetch_active_definitions(conn, "pytest/T01/GENERATOR")
    assert active["Gen_RPM_Avg"] == definition


def test_apply_catalog_changes_versions_instead_of_overwriting(conn):
    t1 = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 5, 13, 0, 0, tzinfo=timezone.utc)
    old = SignalDefinition(signal_key="Gen_RPM_Avg", signal_type="raw", range_max=1700)
    new = SignalDefinition(signal_key="Gen_RPM_Avg", signal_type="raw", range_max=1800)

    apply_catalog_changes(conn, "pytest/T01/GENERATOR", [old], t1)
    apply_catalog_changes(conn, "pytest/T01/GENERATOR", [new], t2)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT range_max, effective_since, effective_until FROM signal_catalog "
            "WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg' ORDER BY effective_since"
        )
        rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0] == (1700, t1, t2)
    assert rows[1][0] == 1800 and rows[1][2] is None


def test_insert_readings_and_upsert_latest_value(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    row = (now, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1249.0, None)
    assert insert_readings(conn, [row]) == 1
    upsert_latest_values(conn, [row])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT value_numeric FROM silver_latest_value WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'")
        assert cur.fetchone() == (1249.0,)


def test_upsert_latest_value_ignores_an_older_arrival(conn):
    older = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 9, 5, 13, 0, 0, tzinfo=timezone.utc)
    upsert_latest_values(conn, [(newer, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 2.0, None)])
    upsert_latest_values(conn, [(older, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1.0, None)])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT value_numeric FROM silver_latest_value WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'")
        assert cur.fetchone() == (2.0,)


def test_insert_events(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    row = (now, "pytest/T01/GENERATOR", "alarms", {"signal": "Gen_RPM_Avg", "severity": "WARNING"}, "unknown")
    assert insert_events(conn, [row]) == 1
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM silver_events WHERE topic = 'pytest/T01/GENERATOR' AND event_key = 'alarms'")
        assert cur.fetchone() == ({"signal": "Gen_RPM_Avg", "severity": "WARNING"},)


def test_insert_readings_with_empty_rows_is_a_noop(conn):
    assert insert_readings(conn, []) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run (with `UNS_SILVER`'s Postgres up, schema applied, and `DATABASE_URL` exported): `pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 3: Implement `db.py`**

```python
# UNS_SILVER/normalizer/app/db.py
"""Postgres access for the Silver normalizer: watermark, bronze reads,
catalog reads/writes, readings/events inserts, latest-value upserts.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 2
(schema) and Section 3 (ingestion logic).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb

from app.catalog import SignalDefinition


@dataclass
class BronzeRow:
    id: int
    time: datetime
    topic: str
    payload: Any


def fetch_watermark(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT last_processed_id FROM silver_ingest_state WHERE id = 1")
        row = cur.fetchone()
    return row[0] if row else 0


def save_watermark(conn: psycopg.Connection, last_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO silver_ingest_state (id, last_processed_id) VALUES (1, %s)
            ON CONFLICT (id) DO UPDATE SET last_processed_id = EXCLUDED.last_processed_id
            """,
            (last_id,),
        )


def fetch_new_bronze_rows(historian_conn: psycopg.Connection, after_id: int, limit: int) -> list[BronzeRow]:
    with historian_conn.cursor() as cur:
        cur.execute(
            "SELECT id, time, topic, payload FROM mqtt_messages WHERE id > %s ORDER BY id LIMIT %s",
            (after_id, limit),
        )
        return [BronzeRow(id=r[0], time=r[1], topic=r[2], payload=r[3]) for r in cur.fetchall()]


def fetch_active_definitions(conn: psycopg.Connection, topic: str) -> dict[str, SignalDefinition]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT signal_key, signal_type, unit, data_type, range_min, range_max,
                   thresholds, description, source_version
            FROM signal_catalog
            WHERE topic = %s AND effective_until IS NULL
            """,
            (topic,),
        )
        return {
            row[0]: SignalDefinition(
                signal_key=row[0], signal_type=row[1], unit=row[2], data_type=row[3],
                range_min=row[4], range_max=row[5], thresholds=row[6], description=row[7],
                source_version=row[8],
            )
            for row in cur.fetchall()
        }


def apply_catalog_changes(
    conn: psycopg.Connection, topic: str, changed: list[SignalDefinition], observed_at: datetime
) -> None:
    with conn.cursor() as cur:
        for definition in changed:
            cur.execute(
                """
                UPDATE signal_catalog SET effective_until = %s
                WHERE topic = %s AND signal_key = %s AND effective_until IS NULL
                """,
                (observed_at, topic, definition.signal_key),
            )
            cur.execute(
                """
                INSERT INTO signal_catalog
                    (topic, signal_key, signal_type, unit, data_type, range_min, range_max,
                     thresholds, description, source_version, effective_since, effective_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """,
                (
                    topic, definition.signal_key, definition.signal_type, definition.unit,
                    definition.data_type, definition.range_min, definition.range_max,
                    Jsonb(definition.thresholds) if definition.thresholds is not None else None,
                    definition.description, definition.source_version, observed_at,
                ),
            )


def insert_readings(conn: psycopg.Connection, rows: Iterable[tuple]) -> int:
    """Each row: (time, topic, signal_key, signal_type, value_numeric, value_text)."""
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver_readings (time, topic, signal_key, signal_type, value_numeric, value_text)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def insert_events(conn: psycopg.Connection, rows: Iterable[tuple]) -> int:
    """Each row: (time, topic, event_key, payload, signal_type)."""
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver_events (time, topic, event_key, payload, signal_type)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(t, topic, key, Jsonb(payload), st) for (t, topic, key, payload, st) in rows],
        )
    return len(rows)


def upsert_latest_values(conn: psycopg.Connection, rows: Iterable[tuple]) -> None:
    """Same row shape as `insert_readings`: (time, topic, signal_key, signal_type,
    value_numeric, value_text) — callers can pass the same list to both."""
    rows = list(rows)
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric, value_text)
            VALUES (%(topic)s, %(signal_key)s, %(signal_type)s, %(time)s, %(value_numeric)s, %(value_text)s)
            ON CONFLICT (topic, signal_key) DO UPDATE SET
                signal_type = EXCLUDED.signal_type,
                time = EXCLUDED.time,
                value_numeric = EXCLUDED.value_numeric,
                value_text = EXCLUDED.value_text
            WHERE EXCLUDED.time >= silver_latest_value.time
            """,
            [
                {"time": t, "topic": topic, "signal_key": key, "signal_type": st,
                 "value_numeric": vn, "value_text": vt}
                for (t, topic, key, st, vn, vt) in rows
            ],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(uns-silver): add Postgres access layer for catalog, readings, events"
```

---

## Task 8: `retention.py`

**Files:**
- Create: `UNS_SILVER/normalizer/app/retention.py`
- Test: `UNS_SILVER/normalizer/tests/test_retention.py`

**Interfaces:**
- Consumes: `app.config.Settings` (Task 3).
- Produces: `apply_policies(conn: psycopg.Connection, settings: Settings) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# UNS_SILVER/normalizer/tests/test_retention.py
import os

import psycopg
import pytest

from app.config import load_settings
from app.retention import apply_policies

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    yield connection
    connection.close()


def test_apply_policies_does_not_raise(conn):
    settings = load_settings({
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "365",
    })
    apply_policies(conn, settings)


def test_apply_policies_is_idempotent(conn):
    settings = load_settings({
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "0",
    })
    apply_policies(conn, settings)
    apply_policies(conn, settings)  # must not raise on re-application
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retention.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.retention'`

- [ ] **Step 3: Implement `retention.py`**

```python
# UNS_SILVER/normalizer/app/retention.py
"""Applies TimescaleDB compression + retention policies to Silver's own
hypertables, idempotently, from configured settings. Applies only to
UNS_SILVER's own tables — never touches UNS_HISTORIAN's bronze retention.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 4.
"""
from __future__ import annotations

import psycopg
from psycopg import sql

from app.config import Settings

_COMPRESSED_HYPERTABLES = ("silver_readings", "silver_events")
_AGGREGATE_RETENTION_SETTINGS = {
    "silver_readings_1m": "agg_1m_retention_days",
    "silver_readings_1h": "agg_1h_retention_days",
}


def apply_policies(conn: psycopg.Connection, settings: Settings) -> None:
    with conn.cursor() as cur:
        for table in _COMPRESSED_HYPERTABLES:
            cur.execute(sql.SQL("ALTER TABLE {} SET (timescaledb.compress)").format(sql.Identifier(table)))
            cur.execute("SELECT remove_compression_policy(%s::regclass, if_exists => TRUE)", (table,))
            cur.execute(
                "SELECT add_compression_policy(%s::regclass, %s::interval)",
                (table, f"{settings.raw_compress_after_days} days"),
            )
            cur.execute("SELECT remove_retention_policy(%s::regclass, if_exists => TRUE)", (table,))
            cur.execute(
                "SELECT add_retention_policy(%s::regclass, %s::interval)",
                (table, f"{settings.raw_retention_days} days"),
            )

        for table, setting_name in _AGGREGATE_RETENTION_SETTINGS.items():
            days = getattr(settings, setting_name)
            cur.execute("SELECT remove_retention_policy(%s::regclass, if_exists => TRUE)", (table,))
            if days > 0:
                cur.execute(
                    "SELECT add_retention_policy(%s::regclass, %s::interval)", (table, f"{days} days")
                )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retention.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/retention.py tests/test_retention.py
git commit -m "feat(uns-silver): add configurable compression/retention policies"
```

---

## Task 9: `batch.py` — orchestration

**Files:**
- Create: `UNS_SILVER/normalizer/app/batch.py`
- Test: `UNS_SILVER/normalizer/tests/test_batch.py`

**Interfaces:**
- Consumes: `app.topics.classify_topic` (Task 4), `app.flatten.flatten_payload` (Task 5), `app.catalog.extract_definitions`/`diff_definitions` (Task 6), all of `app.db` (Task 7), `app.config.Settings` (Task 3).
- Produces: `process_batch(historian_conn, silver_conn, settings: Settings) -> int` — processes up to `settings.batch_size` new bronze rows, commits `silver_conn` once atomically (writes + advanced watermark), returns the number of bronze rows processed (`0` if none pending).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_SILVER/normalizer/tests/test_batch.py
import os
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.batch import process_batch
from app.config import load_settings
from app.db import fetch_watermark, save_watermark

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)

SETTINGS = load_settings({"NORMALIZER_BATCH_SIZE": "10", "MAX_FLATTEN_DEPTH": "6", "MAX_FLATTEN_KEYS_PER_MESSAGE": "500"})


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mqtt_messages (
            id BIGSERIAL, time TIMESTAMPTZ NOT NULL, topic TEXT NOT NULL, payload JSONB
        )
        """
    )
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value", "mqtt_messages"):
        connection.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    save_watermark(connection, 0)
    connection.commit()
    yield connection
    connection.rollback()
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value", "mqtt_messages"):
        connection.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    connection.commit()
    connection.close()


def _insert_bronze(conn, topic: str, payload: dict, time: datetime) -> None:
    conn.execute(
        "INSERT INTO mqtt_messages (time, topic, payload) VALUES (%s, %s, %s)",
        (time, topic, Jsonb(payload)),
    )
    conn.commit()


def test_no_new_rows_returns_zero(conn):
    assert process_batch(conn, conn, SETTINGS) == 0


def test_descriptive_message_populates_catalog(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(
        conn, "pytest/T01/GENERATOR/_descriptive",
        {"schema_version": "1.0.0", "signals": {"Gen_RPM_Avg": {"unit": "RPM", "range_max": 1700}}},
        now,
    )
    processed = process_batch(conn, conn, SETTINGS)
    assert processed == 1
    with conn.cursor() as cur:
        cur.execute(
            "SELECT signal_type, unit FROM signal_catalog WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'"
        )
        assert cur.fetchone() == ("raw", "RPM")


def test_informative_message_produces_reading_tagged_from_catalog(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(
        conn, "pytest/T01/GENERATOR/_descriptive",
        {"schema_version": "1.0.0", "signals": {"Gen_RPM_Avg": {"unit": "RPM"}}},
        now,
    )
    _insert_bronze(conn, "pytest/T01/GENERATOR/_informative", {"timestamp": "2026-09-05T12:00:05Z", "Gen_RPM_Avg": 1249.0}, now)

    processed = process_batch(conn, conn, SETTINGS)
    assert processed == 2

    with conn.cursor() as cur:
        cur.execute(
            "SELECT signal_type, value_numeric FROM silver_readings WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'"
        )
        assert cur.fetchone() == ("raw", 1249.0)
        cur.execute(
            "SELECT value_numeric FROM silver_latest_value WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'"
        )
        assert cur.fetchone() == (1249.0,)


def test_uncataloged_signal_is_tagged_unknown_not_dropped(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(conn, "pytest/T01/GENERATOR/_informative", {"Mystery_Signal": 42.0}, now)
    process_batch(conn, conn, SETTINGS)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT signal_type FROM silver_readings WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Mystery_Signal'"
        )
        assert cur.fetchone() == ("unknown",)


def test_analytical_array_of_objects_becomes_event(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "status": "WARNING",
        "alarms": [{"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4}],
    }
    _insert_bronze(conn, "pytest/T01/GENERATOR/_analytical", payload, now)
    process_batch(conn, conn, SETTINGS)
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM silver_events WHERE topic = 'pytest/T01/GENERATOR' AND event_key = 'alarms'")
        assert cur.fetchone() == ({"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4},)


def test_watermark_advances_and_reprocessing_is_a_noop(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(conn, "pytest/T01/GENERATOR/_informative", {"Gen_RPM_Avg": 1.0}, now)
    process_batch(conn, conn, SETTINGS)
    watermark_after_first = fetch_watermark(conn)
    assert process_batch(conn, conn, SETTINGS) == 0
    assert fetch_watermark(conn) == watermark_after_first
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.batch'`

- [ ] **Step 3: Implement `batch.py`**

```python
# UNS_SILVER/normalizer/app/batch.py
"""Orchestrates one processing cycle: fetch new bronze rows, route each by
topic suffix (catalog update vs. flatten-to-readings/events), and commit
everything — writes and the advanced watermark — atomically.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3.
"""
from __future__ import annotations

import logging

import psycopg

from app import catalog, db, flatten, topics
from app.config import Settings

logger = logging.getLogger("uns_silver.normalizer")

_VALUE_SUFFIXES = ("informative", "analytical")


def process_batch(
    historian_conn: psycopg.Connection, silver_conn: psycopg.Connection, settings: Settings
) -> int:
    last_id = db.fetch_watermark(silver_conn)
    rows = db.fetch_new_bronze_rows(historian_conn, last_id, settings.batch_size)
    if not rows:
        return 0

    reading_rows: list[tuple] = []
    event_rows: list[tuple] = []
    max_id = last_id

    for row in rows:
        base_topic, suffix = topics.classify_topic(row.topic)
        payload = row.payload if isinstance(row.payload, dict) else {}

        if suffix == "descriptive":
            incoming_defs = catalog.extract_definitions(payload)
            active = db.fetch_active_definitions(silver_conn, base_topic)
            changed = catalog.diff_definitions(active, incoming_defs)
            if changed:
                db.apply_catalog_changes(silver_conn, base_topic, changed, row.time)

        elif suffix in _VALUE_SUFFIXES:
            active = db.fetch_active_definitions(silver_conn, base_topic)
            flattened = flatten.flatten_payload(payload, settings.max_flatten_depth, settings.max_flatten_keys)
            if flattened.truncated:
                logger.warning("Payload truncated during flattening: topic=%s", row.topic)
            for value in flattened.values:
                signal_type = active[value.path].signal_type if value.path in active else "unknown"
                reading_rows.append(
                    (row.time, base_topic, value.path, signal_type, value.value_numeric, value.value_text)
                )
            for event in flattened.events:
                signal_type = active[event.event_key].signal_type if event.event_key in active else "unknown"
                event_rows.append((row.time, base_topic, event.event_key, event.payload, signal_type))

        max_id = row.id

    if reading_rows:
        db.insert_readings(silver_conn, reading_rows)
        db.upsert_latest_values(silver_conn, reading_rows)
    if event_rows:
        db.insert_events(silver_conn, event_rows)

    db.save_watermark(silver_conn, max_id)
    silver_conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Run the full normalizer test suite**

Run: `pytest tests/ -v`
Expected: PASS (all tests across all tasks so far)

- [ ] **Step 6: Commit**

```bash
git add app/batch.py tests/test_batch.py
git commit -m "feat(uns-silver): add batch processing orchestration"
```

---

## Task 10: `main.py`, root compose wiring, and end-to-end verification

**Files:**
- Create: `UNS_SILVER/normalizer/app/main.py`
- Create: `UNS_SILVER/normalizer/Dockerfile`
- Create: `UNS_SILVER/README.md`
- Modify: `docker-compose.yml` (repo root)

**Interfaces:**
- Produces: the `uns_silver_normalizer` process entrypoint (`python -m app.main`). No dedicated unit test — matches `UNS_HISTORIAN`'s own `main.py`, which is verified only through its constituent, already-tested modules (`batch.py` here) plus manual/end-to-end verification.

- [ ] **Step 1: Implement `main.py`**

```python
# UNS_SILVER/normalizer/app/main.py
"""Entrypoint: connects to uns_silver_postgres and uns_historian_postgres
(read-only in practice), applies retention/compression policies, LISTENs
for `silver_updates` notifications from the historian ingestor, and
processes newly-arrived bronze rows. Falls back to polling every
NORMALIZER_POLL_INTERVAL_SECONDS in case a notification is missed (e.g.
across a restart).

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3.
"""
from __future__ import annotations

import logging
import signal
import threading

import psycopg

from app import retention
from app.batch import process_batch
from app.config import Settings, load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("uns_silver.normalizer")


def _process_until_caught_up(
    historian_conn: psycopg.Connection, silver_conn: psycopg.Connection, settings: Settings
) -> None:
    while True:
        processed = process_batch(historian_conn, silver_conn, settings)
        if processed:
            logger.info("Processed %d bronze row(s)", processed)
        if processed < settings.batch_size:
            break


def main() -> None:
    settings = load_settings()

    silver_conn = psycopg.connect(settings.database_url, autocommit=False)
    retention.apply_policies(silver_conn, settings)

    historian_conn = psycopg.connect(settings.historian_database_url, autocommit=True)
    historian_conn.execute("LISTEN silver_updates")

    stop_event = threading.Event()

    def _handle_sigterm(signum, frame):
        logger.info("Received SIGTERM, shutting down")
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("Silver normalizer started, listening for silver_updates")
    _process_until_caught_up(historian_conn, silver_conn, settings)

    while not stop_event.is_set():
        # Blocks up to poll_interval_seconds; wakes early on a NOTIFY, or
        # simply times out (empty iteration) as the polling fallback.
        for _ in historian_conn.notifies(timeout=settings.poll_interval_seconds):
            break
        if stop_event.is_set():
            break
        try:
            _process_until_caught_up(historian_conn, silver_conn, settings)
        except psycopg.OperationalError:
            logger.exception("Database error while processing batch, retrying next cycle")

    silver_conn.close()
    historian_conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the Dockerfile**

```dockerfile
# UNS_SILVER/normalizer/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests

CMD ["python", "-m", "app.main"]
```

- [ ] **Step 3: Write the README**

```markdown
# UNS Silver

Independently-deployable normalization service that turns `UNS_HISTORIAN`'s
raw bronze JSONB into a versioned semantic catalog, typed per-signal
readings, an event log, and a latest-value cache — the foundation for a
future LLM/agent query layer.

See `docs/superpowers/specs/2026-09-05-uns-silver-design.md` for the full
design.

## Prerequisites

`UNS_HISTORIAN` must already be running, with Task 1's `id` column and
`NOTIFY` hook applied (fresh installs get both from `init.sql`; an existing
instance needs the migration in `UNS_HISTORIAN/postgres/migrations/`):

```bash
cd ../UNS_HISTORIAN
docker compose up -d
```

## Quickstart

```bash
cp .env.example .env
./scripts/up.sh
./scripts/status.sh
```

- Postgres (TimescaleDB): `localhost:5436` (see `.env` for credentials).
- pgAdmin: http://localhost:5052 — the "UNS Silver" server connection is
  pre-registered; you'll be prompted for the Postgres password on first
  connect.

## Operations

- `./scripts/up.sh` — build and start all containers.
- `./scripts/down.sh` — stop and remove containers.
- `./scripts/restart.sh [service]` — restart one service, or the whole stack.
- `./scripts/logs.sh [service]` — tail logs (all services, or one).
- `./scripts/status.sh` — show container status.

## Verifying normalization is working

```bash
./scripts/logs.sh silver_normalizer
```
Look for `Silver normalizer started` and periodic `Processed N bronze row(s)`
lines whenever `UNS_HISTORIAN` ingests new messages. To inspect stored data,
use pgAdmin or:

```bash
docker compose exec silver_postgres psql -U silver -d uns_silver \
  -c "SELECT time, topic, signal_key, signal_type, value_numeric FROM silver_readings ORDER BY time DESC LIMIT 20;"
```
```

- [ ] **Step 4: Wire `UNS_SILVER` into the root `docker-compose.yml`**

Edit the root `docker-compose.yml`:
- Update the header comment's stack list to mention `UNS_SILVER`.
- Add `- UNS_SILVER/docker-compose.yml` to the `include:` list.

```yaml
name: inari_uns

# Orchestrates the four independent stacks together in one project:
#   - UNS_MANAGER: Node-RED, EMQX, backend/frontend, Postgres
#   - UNS_HISTORIAN: TimescaleDB + pgAdmin + MQTT ingestor
#   - UNS_DASHBOARD: Postgres, Redis, MQTT->Redis bridge, backend/frontend
#   - UNS_SILVER: TimescaleDB + pgAdmin + bronze-to-silver normalizer
#
# Each stack keeps working standalone too (`cd UNS_MANAGER && docker compose up`,
# `cd UNS_HISTORIAN && docker compose up`, `cd UNS_DASHBOARD && docker compose up`,
# `cd UNS_SILVER && docker compose up`) — this file just includes all four
# under one project so they always come up together, in the right order, on
# the same uns_net network.
#
# Usage: docker compose up -d   (from this directory)

include:
  - UNS_MANAGER/docker-compose.yml
  - UNS_HISTORIAN/docker-compose.yml
  - UNS_DASHBOARD/docker-compose.yml
  - UNS_SILVER/docker-compose.yml

# Cross-stack overrides, only meaningful once both stacks are merged into
# one project (UNS_HISTORIAN's own compose file can't express these
# standalone, since emqx/uns_net don't exist when that file runs alone):
services:
  # The ingestor can now wait on emqx's health too, not just its own db.
  ingestor:
    depends_on:
      emqx:
        condition: service_healthy

networks:
  # UNS_HISTORIAN declares this as an external network so it can run
  # standalone against an already-running UNS_MANAGER. Here, UNS_MANAGER's
  # own `uns_net` (same physical network, both pinned to the name
  # uns_manager_uns_net) is included in the very same `up`, so it must not
  # be required to pre-exist.
  uns_manager_net:
    external: false
```

- [ ] **Step 5: Full-stack manual verification**

```bash
cd G:/00_data/00_Formacion/INARI_V05
docker compose up -d --build
docker compose ps
```
Expected: all containers healthy/running, including `uns_silver_postgres`, `uns_silver_pgadmin`, `uns_silver_normalizer`.

Publish a test message through `UNS_MANAGER` (or `mosquitto_pub` against `localhost:1883`) to a topic like `pytest/T01/GENERATOR/_descriptive` with a `signals` map, then an `_informative` message with a matching key. Confirm:

```bash
docker compose exec uns_silver_postgres psql -U silver -d uns_silver \
  -c "SELECT topic, signal_key, signal_type FROM signal_catalog;"
docker compose exec uns_silver_postgres psql -U silver -d uns_silver \
  -c "SELECT topic, signal_key, signal_type, value_numeric FROM silver_readings ORDER BY time DESC LIMIT 10;"
```
Expected: the catalog row and the corresponding reading, tagged with the correct `signal_type`.

- [ ] **Step 6: Commit**

```bash
cd G:/00_data/00_Formacion/INARI_V05
git add UNS_SILVER/normalizer/app/main.py UNS_SILVER/normalizer/Dockerfile UNS_SILVER/README.md docker-compose.yml
git commit -m "feat(uns-silver): add entrypoint, Dockerfile, and wire into root compose"
```
