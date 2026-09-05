# UNS MCP

Read-only MCP (Model Context Protocol) server exposing `UNS_SILVER`'s
semantic layer -- current values, historical trends, signal catalog,
active alarms -- to any LLM/agent, over two transports.

See `docs/superpowers/specs/2026-09-05-uns-mcp-design.md` for the full
design.

## Prerequisites

`UNS_SILVER` must already be running, with the `silver_reader` role
applied (see `UNS_SILVER`'s own docs if not):

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

The server listens at `http://localhost:8090/mcp` (or whatever
`MCP_HTTP_PORT` you set). Every request needs the header
`X-MCP-API-Key: <your MCP_API_KEY>`.

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

Note the database URL here uses `localhost:5436` (the host-exposed port),
not `uns_silver_postgres:5432` (the Docker-internal name) -- this process
runs on your host machine, not inside the Docker network.

`PYTHONPATH` is required: the `mcp` CLI only adds the target file's own
directory (`.../server/app`) to `sys.path`, not its parent, so `server.py`'s
`from app import db` fails with `ModuleNotFoundError: No module named 'app'`
unless `server/` itself is importable. Set it to the absolute path of
`UNS_MCP/server` (same directory as `app/server.py`'s parent).

## Operations (HTTP container)

- `./scripts/up.sh` / `down.sh` / `restart.sh [service]` / `logs.sh [service]` / `status.sh`
