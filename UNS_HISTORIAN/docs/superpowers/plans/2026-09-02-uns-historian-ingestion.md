# UNS Historian Ingestion Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up an independently-deployable Docker service (`UNS_HISTORIAN/`) that subscribes to every MQTT message on the existing EMQX broker and durably stores it in a TimescaleDB hypertable, so later milestones (query API, dashboards, LLM analysis) have real historical data.

**Architecture:** A Postgres+TimescaleDB container and a pgAdmin container (for manual verification) run on a private `historian_net`; a Python ingestor container joins both `historian_net` and the UNS Manager's existing `uns_net` to reach EMQX. The ingestor normalizes every MQTT message into one or more timestamped readings, deduplicates against an in-memory per-topic cache (seeded from the DB at startup), buffers new rows, and flushes them to Postgres in batches. No query API or frontend in this milestone.

**Tech Stack:** Python 3.12, `paho-mqtt` 2.x, `psycopg` 3.x (`psycopg[binary]`), `pytest`, `timescale/timescaledb:latest-pg16`, `dpage/pgadmin4`, Docker Compose.

**Spec:** `UNS_HISTORIAN/docs/superpowers/specs/2026-09-02-uns-historian-design.md`

## Global Constraints

- Subscribe with topic filter `#` on EMQX (captures every UNS message; `$SYS/#` is excluded automatically by MQTT spec semantics for `#` subscriptions).
- Storage is generic: one row per reading = `(time, topic, payload JSONB, raw_payload TEXT, qos, retain)`. No per-signal columns, no fixed signal catalog.
- `time` = the reading's own top-level `timestamp` key (ISO 8601, parsed) when present and valid; otherwise MQTT arrival time.
- A JSON list payload is split into one reading per list element (each with its own `time` extraction).
- An empty MQTT payload is stored as one reading with `payload = NULL, raw_payload = NULL` (represents a "topic cleared" event) — never dropped.
- A non-JSON payload is stored with `payload = NULL, raw_payload = <decoded text>` — never dropped.
- Deduplication: compare the full normalized value (`payload` if not `None`, else `raw_payload`) against the last stored value for that `topic`; skip the insert if identical. Applies uniformly — no special-casing on the MQTT `retain` flag.
- No retention/compression policy, no query API, no frontend view in this milestone (explicitly deferred in the spec).
- New dedicated Postgres+TimescaleDB instance — **not** shared with `UNS_MANAGER`'s Postgres (which lacks the TimescaleDB extension).
- Networks: `historian_net` (internal bridge, private to this stack) + `uns_net` (external, real Docker name `uns_manager_uns_net` — verified via `docker compose config` in `UNS_MANAGER/`, overridable via `UNS_MANAGER_NETWORK_NAME` env var).
- Flush buffered rows to Postgres every `FLUSH_INTERVAL_SECONDS` (default 2s) or `FLUSH_MAX_ROWS` (default 500), whichever first. Cap the in-memory buffer at `BUFFER_MAX_ROWS` (default 20000); past that, drop the oldest row and log a warning.
- All code, comments, and commit messages in English (per repo `AGENTS.md`). Required `scripts/{up,down,restart,logs,status}.sh` per `AGENTS.md`.
- Host ports: Postgres `5434` (avoids `UNS_MANAGER`'s `5433`), pgAdmin `5051`. No other host ports exposed.

---

## Task 1: TimescaleDB schema + Postgres/pgAdmin containers

**Files:**
- Create: `UNS_HISTORIAN/postgres/init.sql`
- Create: `UNS_HISTORIAN/pgadmin/servers.json`
- Create: `UNS_HISTORIAN/docker-compose.yml`
- Create: `UNS_HISTORIAN/.env.example`
- Create: `UNS_HISTORIAN/.gitignore`

**Interfaces:**
- Produces: table `mqtt_messages(time TIMESTAMPTZ, topic TEXT, payload JSONB, raw_payload TEXT, qos SMALLINT, retain BOOLEAN)` as a TimescaleDB hypertable partitioned on `time`, with index `(topic, time DESC)`. Service `postgres` reachable at hostname `postgres:5432` from `historian_net`. Service `pgadmin` reachable at `http://localhost:5051`.

- [ ] **Step 1: Write the schema file**

```sql
-- UNS_HISTORIAN/postgres/init.sql
-- UNS Historian schema — generic MQTT message capture.
-- See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 2.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS mqtt_messages (
    time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,
    payload      JSONB,
    raw_payload  TEXT,
    qos          SMALLINT NOT NULL,
    retain       BOOLEAN NOT NULL
);

SELECT create_hypertable('mqtt_messages', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_mqtt_messages_topic_time ON mqtt_messages (topic, time DESC);
```

- [ ] **Step 2: Write the pgAdmin pre-registered connection**

```json
{
  "Servers": {
    "1": {
      "Name": "UNS Historian",
      "Group": "Servers",
      "Host": "postgres",
      "Port": 5432,
      "MaintenanceDB": "uns_historian",
      "Username": "historian",
      "SSLMode": "prefer"
    }
  }
}
```

Note: this only pre-fills connection details. pgAdmin still prompts for the Postgres password on first connect (enter the `POSTGRES_PASSWORD` value) — deliberately not automating this with a `.pgpass` file, to avoid brittle file-permission requirements on Windows bind mounts.

- [ ] **Step 3: Write `docker-compose.yml` (postgres + pgadmin only for now)**

```yaml
version: "3.9"

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: uns_historian_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-historian}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-historianpassword}
      POSTGRES_DB: ${POSTGRES_DB:-uns_historian}
    volumes:
      - historian_postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "${POSTGRES_PORT:-5434}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-historian} -d ${POSTGRES_DB:-uns_historian}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - historian_net

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: uns_historian_pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: ${PGADMIN_DEFAULT_EMAIL:-admin@uns-historian.local}
      PGADMIN_DEFAULT_PASSWORD: ${PGADMIN_DEFAULT_PASSWORD:-pgadminpassword}
      PGADMIN_CONFIG_SERVER_MODE: "False"
    volumes:
      - historian_pgadmin_data:/var/lib/pgadmin
      - ./pgadmin/servers.json:/pgadmin4/servers.json:ro
    ports:
      - "${PGADMIN_PORT:-5051}:80"
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - historian_net
    restart: unless-stopped

volumes:
  historian_postgres_data:
  historian_pgadmin_data:

networks:
  historian_net:
    driver: bridge
```

- [ ] **Step 4: Write `.env.example`**

```
# PostgreSQL (TimescaleDB)
POSTGRES_USER=historian
POSTGRES_PASSWORD=historianpassword
POSTGRES_DB=uns_historian
POSTGRES_PORT=5434

# pgAdmin
PGADMIN_DEFAULT_EMAIL=admin@uns-historian.local
PGADMIN_DEFAULT_PASSWORD=pgadminpassword
PGADMIN_PORT=5051
```

- [ ] **Step 5: Write `.gitignore`**

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 6: Verify manually**

```bash
cd UNS_HISTORIAN
cp .env.example .env
docker compose up -d postgres pgadmin
docker compose ps
```
Expected: both `uns_historian_postgres` and `uns_historian_pgadmin` show as running/healthy.

```bash
docker compose exec postgres psql -U historian -d uns_historian -c "\d mqtt_messages"
docker compose exec postgres psql -U historian -d uns_historian -c "SELECT hypertable_name FROM timescaledb_information.hypertables;"
```
Expected: `\d mqtt_messages` lists the 6 columns; the hypertables query returns one row, `mqtt_messages`.

Open `http://localhost:5051`, log in with the pgAdmin credentials from `.env`, confirm the pre-registered "UNS Historian" server appears (password prompt on first connect is expected).

- [ ] **Step 7: Commit**

```bash
git add UNS_HISTORIAN/postgres UNS_HISTORIAN/pgadmin UNS_HISTORIAN/docker-compose.yml UNS_HISTORIAN/.env.example UNS_HISTORIAN/.gitignore
git commit -m "$(cat <<'EOF'
feat(historian): TimescaleDB schema + Postgres/pgAdmin containers

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 2: Ingestor project skeleton + Dockerfile + compose wiring

**Files:**
- Create: `UNS_HISTORIAN/ingestor/Dockerfile`
- Create: `UNS_HISTORIAN/ingestor/requirements.txt`
- Create: `UNS_HISTORIAN/ingestor/app/__init__.py`
- Create: `UNS_HISTORIAN/ingestor/tests/__init__.py`
- Modify: `UNS_HISTORIAN/docker-compose.yml` (add `uns_net` external network + `ingestor` service)
- Modify: `UNS_HISTORIAN/.env.example` (add EMQX/MQTT/flush/network vars)

**Interfaces:**
- Consumes: nothing yet (empty package).
- Produces: buildable image `uns-historian-ingestor:dev`, usable standalone via `docker run --rm uns-historian-ingestor:dev <cmd>` for the pure-unit-test tasks (3–6) without needing the external `uns_net` network. The `ingestor` compose service (used from Task 7 onward) requires `uns_manager_uns_net` to already exist.

- [ ] **Step 1: Confirm the real external network name**

```bash
cd ../UNS_MANAGER
docker compose config | grep -A2 "^networks:"
```
Expected: shows `name: uns_manager_uns_net` under the `uns_net` key (already verified during design — re-check here in case `UNS_MANAGER`'s compose file changed).

- [ ] **Step 2: Write `requirements.txt`**

```
paho-mqtt==2.1.0
psycopg[binary]==3.2.3
pytest==8.3.3
```
If pip cannot resolve one of these exact pins (release availability drifts over time), use the latest available patch within the same major/minor line (`paho-mqtt` 2.x, `psycopg` 3.x, `pytest` 8.x).

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

- [ ] **Step 4: Create empty package markers**

`UNS_HISTORIAN/ingestor/app/__init__.py` — empty file.
`UNS_HISTORIAN/ingestor/tests/__init__.py` — empty file.

- [ ] **Step 5: Add `uns_net` and the `ingestor` service to `docker-compose.yml`**

Add to the `networks:` block (after `historian_net`):
```yaml
  uns_net:
    external: true
    name: ${UNS_MANAGER_NETWORK_NAME:-uns_manager_uns_net}
```

Add a new `ingestor` service (after `pgadmin`):
```yaml
  ingestor:
    build:
      context: ./ingestor
      dockerfile: Dockerfile
    container_name: uns_historian_ingestor
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql://historian:historianpassword@postgres:5432/uns_historian}
      EMQX_HOST: ${EMQX_HOST:-emqx}
      EMQX_PORT: ${EMQX_PORT:-1883}
      MQTT_TOPIC_FILTER: ${MQTT_TOPIC_FILTER:-#}
      MQTT_CLIENT_ID: ${MQTT_CLIENT_ID:-uns-historian-ingestor}
      FLUSH_INTERVAL_SECONDS: ${FLUSH_INTERVAL_SECONDS:-2}
      FLUSH_MAX_ROWS: ${FLUSH_MAX_ROWS:-500}
      BUFFER_MAX_ROWS: ${BUFFER_MAX_ROWS:-20000}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - historian_net
      - uns_net
    restart: unless-stopped
```

- [ ] **Step 6: Add the new env vars to `.env.example`**

Append:
```
DATABASE_URL=postgresql://historian:historianpassword@postgres:5432/uns_historian

# EMQX (must already be running via UNS_MANAGER/docker-compose.yml)
EMQX_HOST=emqx
EMQX_PORT=1883
MQTT_TOPIC_FILTER=#
MQTT_CLIENT_ID=uns-historian-ingestor

# Ingestion buffering
FLUSH_INTERVAL_SECONDS=2
FLUSH_MAX_ROWS=500
BUFFER_MAX_ROWS=20000

# Docker network shared with UNS_MANAGER. This is the REAL network name Docker
# Compose generates for UNS_MANAGER's `uns_net` (project name "uns_manager" +
# network key "uns_net"). Verify with: docker network ls | grep uns_net
# If UNS_MANAGER is renamed or COMPOSE_PROJECT_NAME is set there, update this.
UNS_MANAGER_NETWORK_NAME=uns_manager_uns_net
```

- [ ] **Step 7: Build and smoke-test the image**

```bash
cd UNS_HISTORIAN
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev python -c "print('ok')"
```
Expected: build succeeds; prints `ok`.

- [ ] **Step 8: Commit**

```bash
git add UNS_HISTORIAN/ingestor/Dockerfile UNS_HISTORIAN/ingestor/requirements.txt UNS_HISTORIAN/ingestor/app/__init__.py UNS_HISTORIAN/ingestor/tests/__init__.py UNS_HISTORIAN/docker-compose.yml UNS_HISTORIAN/.env.example
git commit -m "$(cat <<'EOF'
feat(historian): ingestor project skeleton + Dockerfile + compose wiring

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 3: Message normalization (`normalize.py`)

**Files:**
- Create: `UNS_HISTORIAN/ingestor/app/normalize.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_normalize.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `Reading` dataclass with fields `time: datetime`, `payload: Any`, `raw_payload: str | None`. Function `parse_message(raw: bytes, arrival_time: datetime) -> list[Reading]`. Used by `handler.py` (Task 6).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_HISTORIAN/ingestor/tests/test_normalize.py
from datetime import datetime, timezone

from app.normalize import Reading, parse_message

ARRIVAL = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_single_object_without_timestamp_uses_arrival_time():
    raw = b'{"voltage_v": 690, "manufacturer": "Vestas"}'
    readings = parse_message(raw, ARRIVAL)
    assert readings == [
        Reading(time=ARRIVAL, payload={"voltage_v": 690, "manufacturer": "Vestas"}, raw_payload=None)
    ]


def test_single_object_with_valid_timestamp_uses_payload_timestamp():
    raw = b'{"timestamp": "2026-09-02T13:23:24.902Z", "Gen_RPM_Avg": 1008.9}'
    readings = parse_message(raw, ARRIVAL)
    assert len(readings) == 1
    assert readings[0].time == datetime(2026, 9, 2, 13, 23, 24, 902000, tzinfo=timezone.utc)
    assert readings[0].payload["Gen_RPM_Avg"] == 1008.9


def test_list_of_objects_splits_into_multiple_readings():
    raw = (
        b'[{"timestamp": "2026-09-02T13:20:16.748Z", "Gen_RPM_Avg": 1572.5},'
        b' {"timestamp": "2026-09-02T13:20:17.748Z", "Gen_RPM_Avg": 1580.1}]'
    )
    readings = parse_message(raw, ARRIVAL)
    assert len(readings) == 2
    assert readings[0].time == datetime(2026, 9, 2, 13, 20, 16, 748000, tzinfo=timezone.utc)
    assert readings[1].time == datetime(2026, 9, 2, 13, 20, 17, 748000, tzinfo=timezone.utc)


def test_invalid_json_falls_back_to_raw_payload():
    raw = b"not json at all"
    readings = parse_message(raw, ARRIVAL)
    assert readings == [Reading(time=ARRIVAL, payload=None, raw_payload="not json at all")]


def test_empty_payload_returns_single_null_reading():
    readings = parse_message(b"", ARRIVAL)
    assert readings == [Reading(time=ARRIVAL, payload=None, raw_payload=None)]


def test_object_with_unparseable_timestamp_falls_back_to_arrival_time():
    raw = b'{"timestamp": "not-a-date", "value": 1}'
    readings = parse_message(raw, ARRIVAL)
    assert readings[0].time == ARRIVAL
    assert readings[0].payload["timestamp"] == "not-a-date"
```

- [ ] **Step 2: Build the image and run the tests to verify they fail**

```bash
cd UNS_HISTORIAN
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_normalize.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.normalize'`.

- [ ] **Step 3: Write the implementation**

```python
# UNS_HISTORIAN/ingestor/app/normalize.py
"""Normalize a raw MQTT message payload into one or more timestamped readings.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, step 4.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Reading:
    time: datetime
    payload: Any
    raw_payload: str | None


def _extract_time(value: Any, arrival_time: datetime) -> datetime:
    """Use the object's own top-level 'timestamp' key when present and parseable."""
    if isinstance(value, dict) and isinstance(value.get("timestamp"), str):
        try:
            parsed = datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            return arrival_time
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return arrival_time


def parse_message(raw: bytes, arrival_time: datetime) -> list[Reading]:
    """Turn a raw MQTT payload into one or more Readings.

    - Empty payload -> one reading, payload=None, raw_payload=None.
    - Invalid JSON -> one reading, payload=None, raw_payload=<decoded text>.
    - JSON list -> one reading per element.
    - Any other JSON value (object, scalar) -> one reading.
    """
    if not raw:
        return [Reading(time=arrival_time, payload=None, raw_payload=None)]

    text = raw.decode("utf-8", errors="replace")

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return [Reading(time=arrival_time, payload=None, raw_payload=text)]

    if isinstance(parsed, list):
        return [
            Reading(time=_extract_time(item, arrival_time), payload=item, raw_payload=None)
            for item in parsed
        ]

    return [Reading(time=_extract_time(parsed, arrival_time), payload=parsed, raw_payload=None)]
```

- [ ] **Step 4: Rebuild and run the tests to verify they pass**

```bash
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_normalize.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add UNS_HISTORIAN/ingestor/app/normalize.py UNS_HISTORIAN/ingestor/tests/test_normalize.py
git commit -m "$(cat <<'EOF'
feat(historian): normalize raw MQTT payloads into timestamped readings

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 4: Dedup cache (`dedup.py`)

**Files:**
- Create: `UNS_HISTORIAN/ingestor/app/dedup.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_dedup.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `DedupCache(initial: dict[str, Any] | None = None)` with method `should_store(topic: str, comparable: Any) -> bool`. Used by `handler.py` (Task 6) and seeded from `db.load_last_values()` (Task 7) in `main.py` (Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_HISTORIAN/ingestor/tests/test_dedup.py
from app.dedup import DedupCache


def test_new_topic_is_always_stored():
    cache = DedupCache()
    assert cache.should_store("t/1", {"a": 1}) is True


def test_identical_payload_is_skipped():
    cache = DedupCache()
    cache.should_store("t/1", {"a": 1})
    assert cache.should_store("t/1", {"a": 1}) is False


def test_changed_payload_is_stored():
    cache = DedupCache()
    cache.should_store("t/1", {"a": 1})
    assert cache.should_store("t/1", {"a": 2}) is True


def test_repeated_none_is_skipped():
    cache = DedupCache()
    cache.should_store("t/1", None)
    assert cache.should_store("t/1", None) is False


def test_seeded_from_initial_dict_deduplicates_first_message():
    cache = DedupCache(initial={"t/1": {"a": 1}})
    assert cache.should_store("t/1", {"a": 1}) is False


def test_different_topics_are_independent():
    cache = DedupCache()
    cache.should_store("t/1", {"a": 1})
    assert cache.should_store("t/2", {"a": 1}) is True
```

- [ ] **Step 2: Build the image and run the tests to verify they fail**

```bash
cd UNS_HISTORIAN
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_dedup.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dedup'`.

- [ ] **Step 3: Write the implementation**

```python
# UNS_HISTORIAN/ingestor/app/dedup.py
"""In-memory last-value-per-topic cache used to suppress EMQX's retained-message
replay on reconnect without ever dropping genuine telemetry.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, step 5.
"""
from __future__ import annotations

from typing import Any

_MISSING = object()


class DedupCache:
    def __init__(self, initial: dict[str, Any] | None = None):
        self._last: dict[str, Any] = dict(initial or {})

    def should_store(self, topic: str, comparable: Any) -> bool:
        """Return True (and record `comparable` as the new last value) unless it
        is identical to the last stored value for `topic`."""
        previous = self._last.get(topic, _MISSING)
        if previous is not _MISSING and previous == comparable:
            return False
        self._last[topic] = comparable
        return True
```

- [ ] **Step 4: Rebuild and run the tests to verify they pass**

```bash
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_dedup.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add UNS_HISTORIAN/ingestor/app/dedup.py UNS_HISTORIAN/ingestor/tests/test_dedup.py
git commit -m "$(cat <<'EOF'
feat(historian): per-topic dedup cache

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 5: Flush buffer (`buffer.py`)

**Files:**
- Create: `UNS_HISTORIAN/ingestor/app/buffer.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_buffer.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `FlushBuffer(max_rows: int)` with `append(row: Any) -> None`, `drain() -> list[Any]`, `pop_dropped_count() -> int`, `__len__() -> int`. Used by `handler.py` (Task 6) and the flush loop in `main.py` (Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_HISTORIAN/ingestor/tests/test_buffer.py
from app.buffer import FlushBuffer


def test_append_and_drain_returns_rows_in_order():
    buf = FlushBuffer(max_rows=10)
    buf.append("a")
    buf.append("b")
    assert buf.drain() == ["a", "b"]


def test_drain_empties_the_buffer():
    buf = FlushBuffer(max_rows=10)
    buf.append("a")
    buf.drain()
    assert buf.drain() == []
    assert len(buf) == 0


def test_exceeding_max_rows_drops_oldest_and_counts_it():
    buf = FlushBuffer(max_rows=2)
    buf.append("a")
    buf.append("b")
    buf.append("c")
    assert buf.drain() == ["b", "c"]
    assert buf.pop_dropped_count() == 1


def test_pop_dropped_count_resets_to_zero():
    buf = FlushBuffer(max_rows=1)
    buf.append("a")
    buf.append("b")
    buf.pop_dropped_count()
    assert buf.pop_dropped_count() == 0
```

- [ ] **Step 2: Build the image and run the tests to verify they fail**

```bash
cd UNS_HISTORIAN
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_buffer.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.buffer'`.

- [ ] **Step 3: Write the implementation**

```python
# UNS_HISTORIAN/ingestor/app/buffer.py
"""Thread-safe row buffer drained periodically by the flush loop.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, step 6.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any


class FlushBuffer:
    def __init__(self, max_rows: int):
        self._lock = threading.Lock()
        self._rows: deque[Any] = deque()
        self._max_rows = max_rows
        self._dropped = 0

    def append(self, row: Any) -> None:
        with self._lock:
            if len(self._rows) >= self._max_rows:
                self._rows.popleft()
                self._dropped += 1
            self._rows.append(row)

    def __len__(self) -> int:
        with self._lock:
            return len(self._rows)

    def drain(self) -> list[Any]:
        with self._lock:
            rows = list(self._rows)
            self._rows.clear()
            return rows

    def pop_dropped_count(self) -> int:
        with self._lock:
            n = self._dropped
            self._dropped = 0
            return n
```

- [ ] **Step 4: Rebuild and run the tests to verify they pass**

```bash
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_buffer.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add UNS_HISTORIAN/ingestor/app/buffer.py UNS_HISTORIAN/ingestor/tests/test_buffer.py
git commit -m "$(cat <<'EOF'
feat(historian): bounded thread-safe flush buffer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 6: Message handler (`handler.py`)

**Files:**
- Create: `UNS_HISTORIAN/ingestor/app/handler.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_handler.py`

**Interfaces:**
- Consumes: `parse_message` from `app.normalize` (Task 3), `DedupCache` from `app.dedup` (Task 4), `FlushBuffer` from `app.buffer` (Task 5).
- Produces: `handle_message(topic: str, raw: bytes, qos: int, retain: bool, arrival_time: datetime, cache: DedupCache, buffer: FlushBuffer) -> int` (returns rows appended). Called from the MQTT `on_message` callback in `main.py` (Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_HISTORIAN/ingestor/tests/test_handler.py
from datetime import datetime, timezone

from app.buffer import FlushBuffer
from app.dedup import DedupCache
from app.handler import handle_message

ARRIVAL = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_new_reading_is_buffered():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    stored = handle_message("t/1", b'{"value": 1}', 1, True, ARRIVAL, cache, buffer)
    assert stored == 1
    rows = buffer.drain()
    assert rows == [(ARRIVAL, "t/1", {"value": 1}, None, 1, True)]


def test_duplicate_reading_is_not_buffered():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    handle_message("t/1", b'{"value": 1}', 1, True, ARRIVAL, cache, buffer)
    buffer.drain()
    stored = handle_message("t/1", b'{"value": 1}', 1, True, ARRIVAL, cache, buffer)
    assert stored == 0
    assert buffer.drain() == []


def test_list_payload_splits_and_dedupes_independently():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    raw = (
        b'[{"timestamp": "2026-09-02T13:20:16.748Z", "v": 1},'
        b' {"timestamp": "2026-09-02T13:20:17.748Z", "v": 1}]'
    )
    stored = handle_message("t/1", raw, 1, False, ARRIVAL, cache, buffer)
    assert stored == 2  # different timestamps -> never deduped against each other
    assert len(buffer.drain()) == 2
```

- [ ] **Step 2: Build the image and run the tests to verify they fail**

```bash
cd UNS_HISTORIAN
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_handler.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.handler'`.

- [ ] **Step 3: Write the implementation**

```python
# UNS_HISTORIAN/ingestor/app/handler.py
"""Wires message normalization + dedup + buffering together. Kept free of any
paho-mqtt or psycopg dependency so it can be unit tested without a live broker
or database.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, steps 4-5.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.buffer import FlushBuffer
from app.dedup import DedupCache
from app.normalize import parse_message


def handle_message(
    topic: str,
    raw: bytes,
    qos: int,
    retain: bool,
    arrival_time: datetime,
    cache: DedupCache,
    buffer: FlushBuffer,
) -> int:
    """Normalize `raw` into readings, drop duplicates, buffer the rest for
    insertion. Returns the number of rows appended to `buffer`."""
    stored = 0
    for reading in parse_message(raw, arrival_time):
        comparable: Any = reading.payload if reading.payload is not None else reading.raw_payload
        if not cache.should_store(topic, comparable):
            continue
        buffer.append((reading.time, topic, reading.payload, reading.raw_payload, qos, retain))
        stored += 1
    return stored
```

- [ ] **Step 4: Rebuild and run the tests to verify they pass**

```bash
docker build -t uns-historian-ingestor:dev ./ingestor
docker run --rm uns-historian-ingestor:dev pytest tests/test_handler.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add UNS_HISTORIAN/ingestor/app/handler.py UNS_HISTORIAN/ingestor/tests/test_handler.py
git commit -m "$(cat <<'EOF'
feat(historian): message handler wiring normalize+dedup+buffer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 7: Postgres access (`db.py`)

**Prerequisite:** `UNS_MANAGER` must be running so the external `uns_manager_uns_net` network exists (`docker compose run` attaches the `ingestor` service to it even with `--no-deps`):
```bash
cd ../UNS_MANAGER && docker compose up -d
```

**Files:**
- Create: `UNS_HISTORIAN/ingestor/app/db.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_db.py`

**Interfaces:**
- Consumes: a `psycopg.Connection` (caller-managed).
- Produces: `load_last_values(conn) -> dict[str, Any]` (topic → last payload/raw_payload) and `insert_batch(conn, rows: Iterable[tuple]) -> int` (rows = `(time, topic, payload, raw_payload, qos, retain)` tuples, as produced by `handler.handle_message`). Both used by `main.py` (Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# UNS_HISTORIAN/ingestor/tests/test_db.py
import os
from datetime import datetime, timezone

import psycopg
import pytest

from app.db import insert_batch, load_last_values

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL)
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    yield connection
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    connection.close()


def test_insert_batch_writes_rows(conn):
    now = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    rows = [(now, "pytest/topic1", {"value": 1}, None, 1, True)]
    inserted = insert_batch(conn, rows)
    assert inserted == 1
    with conn.cursor() as cur:
        cur.execute("SELECT topic, payload FROM mqtt_messages WHERE topic = 'pytest/topic1'")
        result = cur.fetchone()
    assert result == ("pytest/topic1", {"value": 1})


def test_load_last_values_returns_most_recent_payload_per_topic(conn):
    t1 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 2, 12, 0, 5, tzinfo=timezone.utc)
    insert_batch(
        conn,
        [
            (t1, "pytest/topic2", {"value": 1}, None, 1, False),
            (t2, "pytest/topic2", {"value": 2}, None, 1, False),
        ],
    )
    last_values = load_last_values(conn)
    assert last_values["pytest/topic2"] == {"value": 2}


def test_insert_batch_with_empty_rows_is_a_noop(conn):
    assert insert_batch(conn, []) == 0
```

- [ ] **Step 2: Build, bring up Postgres, and run the tests to verify they fail**

```bash
cd UNS_HISTORIAN
docker compose up -d postgres
docker compose build ingestor
docker compose run --rm --no-deps ingestor pytest tests/test_db.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Write the implementation**

```python
# UNS_HISTORIAN/ingestor/app/db.py
"""Postgres access: startup cache warm-up and batched inserts.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, steps 2 and 6.
"""
from __future__ import annotations

from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb


def load_last_values(conn: psycopg.Connection) -> dict[str, Any]:
    """Seed the dedup cache: last payload (or raw_payload) stored per topic."""
    query = """
        SELECT DISTINCT ON (topic) topic, payload, raw_payload
        FROM mqtt_messages
        ORDER BY topic, time DESC
    """
    result: dict[str, Any] = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for topic, payload, raw_payload in cur.fetchall():
            result[topic] = payload if payload is not None else raw_payload
    return result


def insert_batch(conn: psycopg.Connection, rows: Iterable[tuple]) -> int:
    """Batch-insert (time, topic, payload, raw_payload, qos, retain) rows.
    Returns the number of rows inserted."""
    rows = list(rows)
    if not rows:
        return 0
    params = [
        (time, topic, Jsonb(payload) if payload is not None else None, raw_payload, qos, retain)
        for time, topic, payload, raw_payload, qos, retain in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO mqtt_messages (time, topic, payload, raw_payload, qos, retain)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            params,
        )
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Rebuild and run the tests to verify they pass**

```bash
docker compose build ingestor
docker compose run --rm --no-deps ingestor pytest tests/test_db.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add UNS_HISTORIAN/ingestor/app/db.py UNS_HISTORIAN/ingestor/tests/test_db.py
git commit -m "$(cat <<'EOF'
feat(historian): Postgres access (dedup cache warm-up + batch insert)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 8: Settings + MQTT wiring + entrypoint (`config.py`, `main.py`)

**Prerequisite:** `UNS_MANAGER` running (`docker compose up -d` in `UNS_MANAGER/`) so `emqx` and `uns_manager_uns_net` are available.

**Files:**
- Create: `UNS_HISTORIAN/ingestor/app/config.py`
- Test: `UNS_HISTORIAN/ingestor/tests/test_config.py`
- Create: `UNS_HISTORIAN/ingestor/app/main.py`

**Interfaces:**
- Consumes: `handle_message` (Task 6), `load_last_values`/`insert_batch` (Task 7), `DedupCache` (Task 4), `FlushBuffer` (Task 5).
- Produces: `Settings` dataclass and `load_settings(env: dict[str, str] | None = None) -> Settings`; `main()` entrypoint (module `app.main`, run via `python -m app.main`, already wired as the Dockerfile `CMD`).

- [ ] **Step 1: Write the failing config tests**

```python
# UNS_HISTORIAN/ingestor/tests/test_config.py
from app.config import load_settings


def test_defaults_when_env_is_empty():
    settings = load_settings(env={})
    assert settings.emqx_host == "emqx"
    assert settings.emqx_port == 1883
    assert settings.mqtt_topic_filter == "#"
    assert settings.flush_max_rows == 500


def test_overrides_from_env():
    settings = load_settings(env={"EMQX_HOST": "custom-broker", "FLUSH_MAX_ROWS": "10"})
    assert settings.emqx_host == "custom-broker"
    assert settings.flush_max_rows == 10
```

- [ ] **Step 2: Build and run to verify the config tests fail**

```bash
cd UNS_HISTORIAN
docker compose build ingestor
docker compose run --rm --no-deps ingestor pytest tests/test_config.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Write `config.py`**

```python
# UNS_HISTORIAN/ingestor/app/config.py
"""Environment-variable configuration for the ingestor."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    emqx_host: str
    emqx_port: int
    mqtt_topic_filter: str
    mqtt_client_id: str
    flush_interval_seconds: float
    flush_max_rows: int
    buffer_max_rows: int


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        database_url=e.get(
            "DATABASE_URL", "postgresql://historian:historianpassword@postgres:5432/uns_historian"
        ),
        emqx_host=e.get("EMQX_HOST", "emqx"),
        emqx_port=int(e.get("EMQX_PORT", "1883")),
        mqtt_topic_filter=e.get("MQTT_TOPIC_FILTER", "#"),
        mqtt_client_id=e.get("MQTT_CLIENT_ID", "uns-historian-ingestor"),
        flush_interval_seconds=float(e.get("FLUSH_INTERVAL_SECONDS", "2")),
        flush_max_rows=int(e.get("FLUSH_MAX_ROWS", "500")),
        buffer_max_rows=int(e.get("BUFFER_MAX_ROWS", "20000")),
    )
```

- [ ] **Step 4: Rebuild and run to verify the config tests pass**

```bash
docker compose build ingestor
docker compose run --rm --no-deps ingestor pytest tests/test_config.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Write `main.py`**

```python
# UNS_HISTORIAN/ingestor/app/main.py
"""Entrypoint: connects to Postgres and EMQX, warms the dedup cache, subscribes
to MQTT_TOPIC_FILTER, and flushes buffered rows every FLUSH_INTERVAL_SECONDS
or as soon as the buffer reaches FLUSH_MAX_ROWS, whichever comes first.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg

from app.buffer import FlushBuffer
from app.config import Settings, load_settings
from app.db import insert_batch, load_last_values
from app.dedup import DedupCache
from app.handler import handle_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("uns_historian.ingestor")


def _flush_loop(
    stop_event: threading.Event,
    flush_requested: threading.Event,
    settings: Settings,
    buffer: FlushBuffer,
) -> None:
    conn = psycopg.connect(settings.database_url, autocommit=False)
    try:
        while not stop_event.is_set():
            flush_requested.wait(settings.flush_interval_seconds)
            flush_requested.clear()
            rows = buffer.drain()
            if rows:
                try:
                    inserted = insert_batch(conn, rows)
                    logger.info("Flushed %d row(s)", inserted)
                except psycopg.Error:
                    logger.exception("Flush failed, reconnecting and retrying next cycle")
                    conn.close()
                    conn = psycopg.connect(settings.database_url, autocommit=False)
            dropped = buffer.pop_dropped_count()
            if dropped:
                logger.warning("Dropped %d oldest row(s): buffer was full", dropped)
    finally:
        conn.close()


def main() -> None:
    settings = load_settings()

    warm_conn = psycopg.connect(settings.database_url)
    try:
        initial_cache = load_last_values(warm_conn)
    finally:
        warm_conn.close()
    logger.info("Warmed dedup cache with %d topic(s)", len(initial_cache))

    cache = DedupCache(initial=initial_cache)
    buffer = FlushBuffer(max_rows=settings.buffer_max_rows)

    stop_event = threading.Event()
    flush_requested = threading.Event()
    flush_thread = threading.Thread(
        target=_flush_loop, args=(stop_event, flush_requested, settings, buffer), daemon=True
    )
    flush_thread.start()

    def on_connect(client, userdata, connect_flags, reason_code, properties):
        logger.info("Connected to EMQX (reason_code=%s)", reason_code)
        client.subscribe(settings.mqtt_topic_filter, qos=1)

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from EMQX (reason_code=%s)", reason_code)

    def on_message(client, userdata, message):
        arrival_time = datetime.now(timezone.utc)
        handle_message(
            message.topic,
            message.payload,
            message.qos,
            message.retain,
            arrival_time,
            cache,
            buffer,
        )
        if len(buffer) >= settings.flush_max_rows:
            flush_requested.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.connect(settings.emqx_host, settings.emqx_port, keepalive=60)
    try:
        client.loop_forever()
    finally:
        stop_event.set()
        flush_thread.join(timeout=settings.flush_interval_seconds + 5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Full manual verification**

```bash
cd UNS_HISTORIAN
docker compose up -d --build
docker compose logs -f ingestor
```
Expected in logs: `Warmed dedup cache with 0 topic(s)` (first run) then `Connected to EMQX (reason_code=...)`. Leave this running or re-check logs after the next steps.

Publish a test message from a throwaway client attached to the real shared network:
```bash
docker run --rm --network uns_manager_uns_net eclipse-mosquitto mosquitto_pub \
  -h emqx -p 1883 -t "pytest/historian/_informative" \
  -m '{"timestamp":"2026-09-02T12:00:00Z","Gen_RPM_Avg":1000.5}'
```
Wait ~3 seconds (past the default 2s flush interval), then check Postgres:
```bash
docker compose exec postgres psql -U historian -d uns_historian \
  -c "SELECT time, topic, payload FROM mqtt_messages WHERE topic = 'pytest/historian/_informative';"
```
Expected: one row with `payload = {"timestamp": "2026-09-02T12:00:00+00:00", "Gen_RPM_Avg": 1000.5}` and `time = 2026-09-02 12:00:00+00`.

Re-publish the exact same message, wait, re-query: expected still exactly 1 row (deduplicated). Publish again with a different `timestamp`/value, wait, re-query: expected 2 rows now.

Clean up the test data:
```bash
docker compose exec postgres psql -U historian -d uns_historian \
  -c "DELETE FROM mqtt_messages WHERE topic = 'pytest/historian/_informative';"
```

- [ ] **Step 7: Commit**

```bash
git add UNS_HISTORIAN/ingestor/app/config.py UNS_HISTORIAN/ingestor/tests/test_config.py UNS_HISTORIAN/ingestor/app/main.py
git commit -m "$(cat <<'EOF'
feat(historian): settings loader + MQTT-to-Postgres entrypoint

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```

---

## Task 9: Operational scripts + README

**Files:**
- Create: `UNS_HISTORIAN/scripts/up.sh`
- Create: `UNS_HISTORIAN/scripts/down.sh`
- Create: `UNS_HISTORIAN/scripts/restart.sh`
- Create: `UNS_HISTORIAN/scripts/logs.sh`
- Create: `UNS_HISTORIAN/scripts/status.sh`
- Create: `UNS_HISTORIAN/README.md`

**Interfaces:**
- Consumes: `UNS_HISTORIAN/docker-compose.yml` (all prior tasks).
- Produces: nothing consumed by other tasks — this is the final, user-facing operational surface.

- [ ] **Step 1: Write `scripts/up.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build
echo "UNS Historian is starting. Use scripts/status.sh to check container health."
```

- [ ] **Step 2: Write `scripts/down.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
```

- [ ] **Step 3: Write `scripts/restart.sh`**

```bash
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

- [ ] **Step 4: Write `scripts/logs.sh`**

```bash
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

- [ ] **Step 5: Write `scripts/status.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
```

- [ ] **Step 6: Make scripts executable**

```bash
cd UNS_HISTORIAN
chmod +x scripts/*.sh
```

- [ ] **Step 7: Write `README.md`**

```markdown
# UNS Historian

Independently-deployable ingestion service that subscribes to every MQTT
message on the UNS Manager's EMQX broker (`#`) and stores it as generic
JSONB rows in a TimescaleDB hypertable, for later historical/trend analysis.

**This milestone is ingestion + storage only** — no query API, no frontend.
See `docs/superpowers/specs/2026-09-02-uns-historian-design.md` for the full
design.

## Prerequisites

`UNS_MANAGER` must already be running (its `docker-compose.yml` creates the
`uns_manager_uns_net` Docker network and the `emqx` broker this service
connects to):

```bash
cd ../UNS_MANAGER
docker compose up -d
```

## Quickstart

```bash
cp .env.example .env
./scripts/up.sh
./scripts/status.sh
```

- Postgres (TimescaleDB): `localhost:5434` (see `.env` for credentials).
- pgAdmin: http://localhost:5051 — the "UNS Historian" server connection is
  pre-registered; you'll be prompted for the Postgres password (from `.env`)
  on first connect.

## Operations

- `./scripts/up.sh` — build and start all containers.
- `./scripts/down.sh` — stop and remove containers.
- `./scripts/restart.sh [service]` — restart one service, or the whole stack.
- `./scripts/logs.sh [service]` — tail logs (all services, or one).
- `./scripts/status.sh` — show container status.

## Verifying ingestion is working

```bash
./scripts/logs.sh ingestor
```
Look for `Connected to EMQX` and periodic `Flushed N row(s)` lines whenever
UNS Manager activity (or any MQTT publish) occurs. To inspect stored data,
use pgAdmin or:

```bash
docker compose exec postgres psql -U historian -d uns_historian \
  -c "SELECT time, topic FROM mqtt_messages ORDER BY time DESC LIMIT 20;"
```
```

- [ ] **Step 8: Verify the scripts work end to end**

```bash
cd UNS_HISTORIAN
./scripts/up.sh
./scripts/status.sh
./scripts/logs.sh ingestor &
sleep 5 && kill %1
./scripts/restart.sh ingestor
./scripts/down.sh
```
Expected: `up.sh` builds and starts all 3 containers; `status.sh` shows them running; `logs.sh` streams ingestor logs; `restart.sh` cycles the ingestor container; `down.sh` cleanly stops everything.

- [ ] **Step 9: Commit**

```bash
git add UNS_HISTORIAN/scripts UNS_HISTORIAN/README.md
git commit -m "$(cat <<'EOF'
feat(historian): operational scripts + README

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GNTGGJ6vj2A51mm5XjQLqc
EOF
)"
```
