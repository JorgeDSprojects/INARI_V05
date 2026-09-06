# Running this backend's tests

DB-gated tests need `DATABASE_URL` (and, for the historian-touching ones,
`HISTORIAN_DATABASE_URL`) pointing at **test databases**, never at the
real ones the running app/UI use — `tests/conftest.py`'s
`pytest_configure` hook refuses to run otherwise.

## One-time setup

```bash
docker exec uns_dashboard_postgres psql -U dashboard -d uns_dashboard -c "CREATE DATABASE uns_dashboard_test;"
docker exec uns_historian_postgres psql -U historian -d uns_historian -c "CREATE DATABASE uns_historian_test;"

# uns_dashboard_test's schema is created automatically by this app's own
# create_tables() (SQLAlchemy Base.metadata.create_all) — nothing more to do.

# uns_historian_test needs UNS_HISTORIAN's own init script applied once,
# since that schema is TimescaleDB-specific SQL, not SQLAlchemy metadata:
docker cp ../../../UNS_HISTORIAN/postgres/init.sql uns_historian_postgres:/tmp/init_test.sql
docker cp ../../../UNS_HISTORIAN/postgres/migrations/0001_add_silver_support.sql uns_historian_postgres:/tmp/mig0001_test.sql
docker exec uns_historian_postgres psql -U historian -d uns_historian_test -f /tmp/init_test.sql
docker exec uns_historian_postgres psql -U historian -d uns_historian_test -f /tmp/mig0001_test.sql
```

## Running

```bash
DATABASE_URL="postgresql+asyncpg://dashboard:dashboardpassword@localhost:5435/uns_dashboard_test" \
HISTORIAN_DATABASE_URL="postgresql+asyncpg://historian:historianpassword@localhost:5434/uns_historian_test" \
MCP_SERVER_URL="http://localhost:8095/mcp" \
MCP_API_KEY="changeme-local-dev-key" \
pytest -q
```

`MCP_SERVER_URL`/`MCP_API_KEY` are only needed for `test_mcp_client.py`'s
live-server tests; everything else skips cleanly without them.

Never export `DATABASE_URL`/`HISTORIAN_DATABASE_URL` pointing at
`uns_dashboard`/`uns_historian` (no `_test` in the name) to run this
suite — an earlier oversight did exactly that, and a routine test run
littered the real dev database with `pytest-*` dashboards and chat
sessions visible in the actual browser UI. The `pytest_configure` guard
in `conftest.py` now refuses to start if it detects this.
