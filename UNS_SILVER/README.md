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

## Read-only access for UNS_MCP (and other external consumers)

Alongside the full `silver` application role, this stack defines a
read-only `silver_reader` role with `SELECT` on the catalog, readings,
events, latest-value and aggregate tables and nothing else. `UNS_MCP`
connects as `silver_reader`; any future read-only consumer should too,
rather than being handed the `silver` credentials.

Set its password with `SILVER_READER_PASSWORD` in `.env` (default
`silverreaderpassword`); consumers' own connection strings must match.

Fresh installs get the role from `postgres/init.sql` on first boot. An
**already-running** instance needs the migration applied once (additive
and idempotent, so re-running it is harmless):

```bash
docker exec -i uns_silver_postgres psql -U silver -d uns_silver \
  < postgres/migrations/0001_add_silver_reader_role.sql
```

`SILVER_READER_PASSWORD` must already be present in the container's
environment for that to work — if you only just added it to `.env`, run
`./scripts/restart.sh silver_postgres` first.

An external consumer also has to be able to *reach* the database:
`silver_postgres` is joined to `uns_manager_net` (the network shared with
`UNS_MANAGER`, named by `UNS_MANAGER_NETWORK_NAME`) so containers on that
network can connect to it as `uns_silver_postgres:5432`. An instance
created before that network was added to this compose file needs
`./scripts/up.sh` re-run to pick it up. Verify with:

```bash
docker network inspect uns_manager_uns_net --format '{{range .Containers}}{{.Name}} {{end}}'
```

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
