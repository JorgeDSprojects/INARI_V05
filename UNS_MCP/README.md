# UNS MCP

Read-only MCP (Model Context Protocol) server exposing `UNS_SILVER`'s
semantic layer -- current values, historical trends, signal catalog,
active alarms -- to any LLM/agent, over two transports.

See `docs/superpowers/specs/2026-09-05-uns-mcp-design.md` for the full
design.

## Prerequisites

`UNS_SILVER` must already be running, with the `silver_reader` role
applied and its Postgres joined to `uns_manager_net` (see the
"Read-only access for UNS_MCP" section of `UNS_SILVER/README.md`):

```bash
cd ../UNS_SILVER
docker compose up -d
```

## HTTP transport (production / multi-agent use)

```bash
cp .env.example .env
./scripts/up.sh
./scripts/status.sh
```

The server listens at `http://localhost:8095/mcp` (or whatever
`MCP_HTTP_PORT` you set). Every request needs the header
`X-MCP-API-Key: <your MCP_API_KEY>`.

### Before deploying anywhere but your own machine

- **Set a real `MCP_API_KEY`.** The server refuses to start while the key
  is still `changeme-local-dev-key`. `docker-compose.yml` sets
  `MCP_ALLOW_DEFAULT_KEY=true` so a local `docker compose up` still works
  out of the box; drop that override (or set it to `false`) anywhere else.
- **Set `MCP_ALLOWED_HOSTS`** to the names clients actually reach this
  server by. The transport validates the `Host` header for DNS-rebinding
  protection and answers `421 Misdirected Request` to anything unlisted,
  so a client calling `http://some-other-name:8000/mcp` fails until that
  name (with a `:*` port wildcard) is in the list. The default covers
  loopback plus `uns_mcp_server:*`, which is what other containers on
  `uns_manager_net` use.
- The API key travels in a plain header. Put this behind TLS (a reverse
  proxy) for anything crossing an untrusted network.

## stdio transport (local, personal use via Claude Desktop/Code)

This path is **not** run in Docker -- your LLM host launches it directly
on your machine. First, set up a local Python environment:

```bash
cd server
python -m venv .venv
.venv/Scripts/activate   # or: source .venv/bin/activate
pip install -r requirements.txt
```

Then point your host at it. For Claude Desktop, add to
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "uns-silver": {
      "command": "/absolute/path/to/UNS_MCP/server/.venv/bin/mcp",
      "args": ["run", "/absolute/path/to/UNS_MCP/server/app/server.py"],
      "env": {
        "SILVER_DATABASE_URL": "postgresql://silver_reader:silverreaderpassword@localhost:5436/uns_silver",
        "PYTHONPATH": "/absolute/path/to/UNS_MCP/server"
      }
    }
  }
}
```

`"command"` above is the POSIX path. On Windows the venv puts the
launcher somewhere else, so use:

```
"command": "C:\\absolute\\path\\to\\UNS_MCP\\server\\.venv\\Scripts\\mcp.exe"
```

(matching `.venv/Scripts/activate` vs `source .venv/bin/activate` above;
note JSON needs the backslashes doubled).

Note the database URL here uses `localhost:5436` (the host-exposed port),
not `uns_silver_postgres:5432` (the Docker-internal name) -- this process
runs on your host machine, not inside the Docker network.

`PYTHONPATH` is required: the `mcp` CLI only adds the target file's own
directory (`.../server/app`) to `sys.path`, not its parent, so `server.py`'s
`from app import db` fails with `ModuleNotFoundError: No module named 'app'`
unless `server/` itself is importable. Set it to the absolute path of
`UNS_MCP/server` (same directory as `app/server.py`'s parent).

## A note on `list_signals` coverage

`list_signals` reads `signal_catalog`, which `UNS_SILVER` populates from
`_descriptive` MQTT messages. Until a topic has published one, its signals
have no catalog entry -- so on a fresh or partially-cataloged system
`list_signals` can return little or nothing even though `UNS_SILVER` holds
plenty of real data. That is a data-availability gap upstream, not a
failure of this server: `get_current_value` and `get_historical_trend`
work fine against any signal you know the exact `signal_key` for. To see
what is actually queryable right now:

```bash
docker exec uns_silver_postgres psql -U silver -d uns_silver \
  -c "SELECT topic, signal_key FROM silver_latest_value ORDER BY topic, signal_key;"
```

## Operations (HTTP container)

- `./scripts/up.sh` / `down.sh` / `restart.sh [service]` / `logs.sh [service]` / `status.sh`
