import asyncio
import os

import pytest


def _database_name(url: str) -> str:
    # postgresql+asyncpg://user:pass@host:port/dbname
    return url.rsplit("/", 1)[-1].split("?", 1)[0]


def pytest_configure(config):
    """Refuse to run against a database that isn't clearly a test database.

    This backend's DATABASE_URL/HISTORIAN_DATABASE_URL point at the SAME
    Postgres databases the real running app (and its real users, in a
    browser) read and write. Nothing about running `pytest` was ever
    isolated from that -- a dispatched agent's routine test run once
    littered the live dev database with real-looking `pytest-*`
    dashboards and chat sessions, visible in the actual UI, discovered
    only because a human happened to refresh the page at the wrong
    moment. Point these env vars at `uns_dashboard_test`/
    `uns_historian_test` instead (create once with e.g. `docker exec
    uns_dashboard_postgres psql -U dashboard -d uns_dashboard -c
    "CREATE DATABASE uns_dashboard_test;"` -- tables are created
    automatically by this app's own `create_tables()`/`Base.metadata.
    create_all`, there is no migration step to run first).
    """
    for env_var in ("DATABASE_URL", "HISTORIAN_DATABASE_URL"):
        url = os.environ.get(env_var)
        if url and "test" not in _database_name(url).lower():
            raise pytest.UsageError(
                f"{env_var} points at database '{_database_name(url)}', which does not "
                "look like a test database (expected a name containing 'test'). Refusing "
                "to run: this would write directly into the real dev/prod database that "
                "the actual running application and its users see. Point it at a test "
                f"database instead, e.g. one named '{_database_name(url)}_test'."
            )


@pytest.fixture(autouse=True)
def _dispose_shared_db_engines():
    """Dispose app.database's shared engine pools after every test.

    app/database.py creates `engine`/`historian_engine` once at import
    time and keeps them alive for the whole pytest process. Each router
    test's `client` fixture spins up its own `TestClient(app)`, and
    starlette's TestClient runs the app on a brand-new anyio worker
    thread + event loop for every `with TestClient(app) as c:` block.
    asyncpg connections are bound to the loop that created them, so a
    pooled connection opened under one test's loop is unusable once that
    loop is closed and a later test's (different) loop borrows it from
    the pool -- this reproduces regardless of whether either test itself
    fails, purely from sharing one global pool across independently
    loop-scoped TestClient instances.

    Disposing the pool after each test forces the next test's TestClient
    to open fresh, loop-matched connections instead of reusing stale
    ones left over from a previous loop.
    """
    yield
    try:
        from app.database import engine, historian_engine
    except ImportError:
        return

    async def _dispose():
        await engine.dispose()
        await historian_engine.dispose()

    try:
        asyncio.run(_dispose())
    except Exception:
        # Best-effort cleanup; a dispose failure here shouldn't mask the
        # test's own pass/fail result.
        pass
