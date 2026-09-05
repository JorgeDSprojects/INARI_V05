# UNS MCP — Query Server Design Spec
**Date:** 2026-09-05
**Status:** Draft — pending user review
**Scope:** First milestone — a read-only MCP (Model Context Protocol) server exposing `UNS_SILVER`'s semantic layer to LLMs/agents, over both `stdio` (local, personal use) and HTTP (remote, production/multi-agent use). No write actions, no dashboard generation (a later sub-project).

---

## Context

`UNS_SILVER` (previous milestone) built a versioned semantic catalog, typed per-signal readings, an event log, a latest-value cache, and continuous aggregates — but it's only reachable via direct Postgres access. This milestone builds the second sub-project of the LLM/agent roadmap: a query layer an LLM can actually call, using MCP (Model Context Protocol) — the standard by which an LLM host application (Claude Desktop, Claude Code, or a custom agent) discovers and invokes external tools.

MCP has three roles: a **server** (a process exposing tools/resources/prompts over JSON-RPC), a **client** (lives inside the LLM host, discovers and calls the server's tools), and a **transport** (`stdio` — the host launches the server as a local subprocess — or HTTP, for a persistent, remotely-reachable service). This spec builds the server; the client side is whatever LLM host connects to it (out of scope here).

This is explicitly a **read-only query layer** — no dashboard authoring, no write actions of any kind. That's a separate, later sub-project building on top of this one.

---

## Key Decisions (from clarifying questions)

| Decision | Choice |
|---|---|
| Language | Python — consistent with the rest of the stack (`UNS_MANAGER`/`UNS_DASHBOARD` backends are FastAPI/Python, `UNS_HISTORIAN`/`UNS_SILVER` are pure Python), and the official MCP SDK (`mcp`) supports both transports from the same tool-registration code |
| Transport support | Both `stdio` and HTTP from day one, from one shared tool-definition module — not one process serving both simultaneously, but one codebase with two launch modes (`--transport stdio\|http`) |
| `stdio` mode | Not dockerized — run locally by the user's own Claude Desktop/Code, which launches it as a subprocess. No auth needed (trust comes from the user having launched it locally) |
| HTTP mode | A new always-on Docker container (`uns_mcp_server`), for production/multi-agent use, protected by a shared API key |
| Tool surface (v1) | `get_current_value`, `get_historical_trend`, `list_signals`, `list_active_alarms` — the four read patterns that map directly onto Silver's four tables |
| Data source | Read-only connection to `uns_silver_postgres` only — no direct dependency on `UNS_HISTORIAN` or EMQX. Single narrow cross-stack coupling, matching every other module's pattern in this project |
| Database credentials | A new dedicated read-only Postgres role (`silver_reader`, `GRANT SELECT` only) — not a reuse of the full `silver` app credentials. Justified specifically here (unlike elsewhere in the project, which reuses full credentials) because the consumer is an LLM: less predictable input surface than static application code, so DB-level defense in depth is worth the small extra setup |
| Query safety | All queries parameterized (never string-interpolated), matching `UNS_SILVER`'s own convention — the read-only role is defense in depth on top of this, not a substitute for it |
| Historical trend granularity | Reuses Silver's existing continuous aggregates (`silver_readings_1m`/`silver_readings_1h`) rather than recomputing bucketing on the fly — mirrors `UNS_DASHBOARD`'s established point-count-bounding principle, but backed by data Silver already precomputed |
| "Active alarms" semantics | The latest-`time` snapshot of `event_key='alarms'` rows for a topic — not a full historical log. `_analytical` publishes a full snapshot of currently-active alarms each time (deduplicated upstream by Historian when unchanged), so the latest snapshot *is* "current alarms" |
| Auth (HTTP) | A single shared API key (`MCP_API_KEY`), checked on every HTTP request before MCP protocol processing |

---

## Section 1 — Architecture

New sibling folder to `UNS_MANAGER/`, `UNS_HISTORIAN/`, `UNS_DASHBOARD/`, `UNS_SILVER/`: **`UNS_MCP/`**, with its own `docker-compose.yml`, `.env.example`, and `scripts/{up,down,restart,logs,status}.sh` per `AGENTS.md`.

One container for the HTTP path:

- **`uns_mcp_server`** — Python 3.12, official `mcp` SDK. No database of its own. Its only external dependency is a read-only connection to `uns_silver_postgres` via the new `silver_reader` role.

The `stdio` path is the *same* Python package, run locally (not in Docker) by whichever LLM host the user configures — e.g. added to Claude Desktop's or Claude Code's MCP server config, which launches `python -m app.main --transport stdio` as a subprocess when needed.

Networking (HTTP path only): `uns_mcp_server` joins the existing shared external network (compose key `uns_manager_net`, real name `uns_manager_uns_net`) to reach `uns_silver_postgres` — the same single-coupling pattern `UNS_SILVER`'s normalizer already uses to reach `UNS_HISTORIAN`'s Postgres.

```
UNS_SILVER                              UNS_MCP
┌────────────────────────┐             ┌──────────────────────────┐
│ uns_silver_postgres     │◄──SELECT────┤ uns_mcp_server (HTTP)     │
│ (role: silver_reader)   │   only      │  API key required         │
└────────────────────────┘             └───────────────────────────┘
                                               ▲
                                               │ same package,
                                        no Docker, launched locally
                                        Claude Desktop / Code (stdio)
```

### One small additive change to `UNS_SILVER`

Documented and applied in `UNS_SILVER`'s own repo area (same pattern as the additive changes `UNS_SILVER` itself required in `UNS_HISTORIAN`): create the `silver_reader` role and grant it `SELECT` on the five objects this server reads (`signal_catalog`, `silver_readings`, `silver_events`, `silver_latest_value`, `silver_readings_1m`, `silver_readings_1h`). Added to `UNS_SILVER/postgres/init.sql` for fresh installs, plus an idempotent migration snippet for the already-running instance.

---

## Section 2 — Tool Surface (v1)

All four tools are read-only and share one design principle: return values enriched enough for an LLM to answer a human's question without a follow-up call (units, not bare numbers; "not found" made explicit, not silently empty).

### `get_current_value(topic, signal_key)`

Joins `silver_latest_value` with the active catalog row (`signal_catalog` WHERE `effective_until IS NULL`) for that `(topic, signal_key)`. Returns:
```json
{ "topic": "...", "signal_key": "...", "signal_type": "raw|kpi|unknown", "value": 1249.0, "unit": "RPM", "time": "2026-09-05T16:42:00Z" }
```
If no `silver_latest_value` row exists for that pair: an explicit "not found" result (not an empty/null value), so the LLM doesn't misreport silence as zero.

### `get_historical_trend(topic, signal_key, from, to)`

Server picks the source table based on requested range width, mirroring `UNS_DASHBOARD`'s point-count-bounding principle but backed by Silver's precomputed aggregates instead of on-the-fly bucketing:
- range ≤ 1 hour → raw `silver_readings`
- range > 1 hour, up to a threshold where 1-minute buckets would still return a bounded number of points (roughly ≤ 2 days) → `silver_readings_1m`
- longer ranges → `silver_readings_1h` (both aggregates are retained indefinitely by default, so the choice here is about bounding the returned point count, not aggregate availability)

Returns a list of points; shape depends on source (`{time, value}` for raw, `{bucket, avg, min, max, sample_count}` for an aggregate) — the tool result makes clear which it returned.

### `list_signals(topic_prefix)`

Queries the active catalog (`effective_until IS NULL`) filtered by `topic LIKE topic_prefix || '%'`. Returns `[{topic, signal_key, signal_type, unit, description}, ...]` — this is the discovery tool: it lets an LLM find out what it *can* ask about under an asset/line/site before calling the other three, instead of guessing signal names.

### `list_active_alarms(topic)`

Finds `MAX(time)` among `silver_events` rows for that `topic` with `event_key = 'alarms'`, then returns every row at exactly that `time` (they all belong to the same `_analytical` publish — the full snapshot of alarms active as of that moment). Returns `[{severity, signal, current_value, threshold_violated, message, ...}, ...]` — whatever fields the source payload carried, verbatim.

**Deferred, not v1**: a historical alarm log (all past snapshots, not just the latest) — noted in Explicitly Deferred below.

---

## Section 3 — Data Access & Safety

- `app/db.py` holds the four query functions as plain, parameterized-SQL functions — no ORM, matching `UNS_SILVER`'s own convention.
- Connection uses the new `silver_reader` role (`GRANT SELECT` only, no write privileges at the database level) — a second line of defense beyond query parameterization, justified here specifically because the tool-call arguments ultimately originate from an LLM's interpretation of a user's natural-language request, a less constrained input surface than the rest of this project's internal service-to-service calls.
- `app/tools.py` registers the four functions as MCP tools, with no transport-specific code — it works identically whether `main.py` starts it in `stdio` or HTTP mode.
- `app/main.py` is the only transport-aware file: parses `--transport {stdio,http}` and wires the corresponding MCP server runner.

---

## Section 4 — Auth (HTTP transport only)

- `MCP_API_KEY` in `.env`, checked against every incoming HTTP request before it reaches MCP protocol handling — a thin check in front of the server, not part of the MCP protocol itself (MCP has no built-in shared-secret auth primitive at this simple a level; this is an application-level gate).
- `stdio` mode has no equivalent check — trust comes from the user having launched the process locally themselves; there is no network boundary to protect there.

---

## Section 5 — Deployment

```
UNS_MCP/
  server/
    app/
      config.py    -- Settings: SILVER_DATABASE_URL, MCP_API_KEY, HTTP host/port
      db.py         -- the four read-only query functions
      tools.py      -- MCP tool registration, transport-agnostic
      main.py       -- entrypoint; --transport stdio|http
    requirements.txt
    Dockerfile
  docker-compose.yml   -- uns_mcp_server (HTTP) only; stdio is run locally, never dockerized
  .env.example
  scripts/{up,down,restart,logs,status}.sh
  README.md            -- covers BOTH paths: docker-compose for HTTP, and how to point
                           Claude Desktop/Code at the local stdio entrypoint
```

Root `docker-compose.yml` gains a fifth `include:` entry for `UNS_MCP/docker-compose.yml`.

---

## Section 6 — Testing

- **Unit**: the historical-trend range→source-table selection logic; the HTTP auth check (valid/missing/invalid key).
- **Integration**: all four query functions against a live `uns_silver_postgres`, using the `silver_reader` role specifically (not the full `silver` credentials) — so a test also proves the read-only role has exactly the grants it needs, no more, no less.
- **Manual verification, both transports**: configure Claude Desktop/Code locally with `stdio` and confirm a real question ("what's the current RPM of generator T01?") triggers the right tool call; separately, send an authenticated HTTP request against the running container and confirm a valid MCP protocol handshake and tool call succeed, and an unauthenticated one is rejected.

---

## Explicitly deferred (future milestones)

- Any write action (dashboard creation/editing) — the third sub-project in this roadmap, built on top of this one.
- Historical alarm log (only the current snapshot in v1).
- Per-user/per-agent API keys (one shared key for v1, consistent with this project's overall no-fine-grained-auth posture so far).
- Query cost limits beyond the aggregate-based downsampling already inherited from Silver.
- A declared `value_shape` override or any other mechanism affecting Silver's own ingestion — this module only reads what Silver already produces.
