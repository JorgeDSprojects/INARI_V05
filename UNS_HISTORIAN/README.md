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
