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
