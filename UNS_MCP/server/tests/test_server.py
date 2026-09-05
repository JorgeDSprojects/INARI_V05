import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.server import get_current_value, list_active_alarms, list_signals

DATABASE_URL = os.environ.get("SILVER_DATABASE_URL")
SEED_DATABASE_URL = os.environ.get("SEED_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not SEED_DATABASE_URL,
    reason="SILVER_DATABASE_URL (silver_reader role, read-only) and SEED_DATABASE_URL "
    "(full 'silver' role, for fixture setup) must both be set -- see tests/test_db.py's "
    "pytestmark for why both are required.",
)


@pytest.fixture
def seed_conn():
    conn = psycopg.connect(SEED_DATABASE_URL, autocommit=False)
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value"):
        conn.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    conn.commit()
    yield conn
    conn.rollback()
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value"):
        conn.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    conn.commit()
    conn.close()


def test_get_current_value_tool_returns_dict(seed_conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", now, 1249.0),
    )
    seed_conn.commit()

    result = get_current_value(topic="pytest/T01/GENERATOR", signal_key="Gen_RPM_Avg")
    assert result["value"] == 1249.0


def test_get_current_value_tool_raises_tool_error_when_missing(seed_conn):
    with pytest.raises(ToolError):
        get_current_value(topic="pytest/nope", signal_key="nope")


def test_list_signals_tool_returns_list(seed_conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, effective_since) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", "RPM", now),
    )
    seed_conn.commit()

    result = list_signals(topic_prefix="pytest/T01")
    assert any(s["signal_key"] == "Gen_RPM_Avg" for s in result)


def test_list_active_alarms_tool_returns_empty_list_when_none(seed_conn):
    assert list_active_alarms(topic="pytest/no/alarms") == []
