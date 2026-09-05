import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.db import NotFound, get_current_value, get_historical_trend, list_active_alarms, list_signals

DATABASE_URL = os.environ.get("SILVER_DATABASE_URL")
SEED_DATABASE_URL = os.environ.get("SEED_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not SEED_DATABASE_URL,
    reason="SILVER_DATABASE_URL and SEED_DATABASE_URL must both be set. "
    "SILVER_DATABASE_URL uses the read-only silver_reader role (what these tests exercise); "
    "SEED_DATABASE_URL must use the full 'silver' role against the same database, since "
    "silver_reader cannot INSERT the fixture data these tests need. Without both set explicitly, "
    "seeding would silently attempt to INSERT through the read-only role and fail with a "
    "confusing permission-denied error instead of a clear skip.",
)


@pytest.fixture
def conn():
    # A second, full-privilege connection for seeding test data (the
    # silver_reader connection under test must stay strictly read-only).
    seed_url = SEED_DATABASE_URL
    seed_conn = psycopg.connect(seed_url, autocommit=False)
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value"):
        seed_conn.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    seed_conn.commit()

    reader_conn = psycopg.connect(DATABASE_URL, autocommit=True)

    yield seed_conn, reader_conn

    seed_conn.rollback()
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value"):
        seed_conn.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    seed_conn.commit()
    seed_conn.close()
    reader_conn.close()


def test_get_current_value_returns_enriched_result(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, effective_since) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", "RPM", now),
    )
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", now, 1249.0),
    )
    seed_conn.commit()

    result = get_current_value(reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg")
    assert result == {
        "topic": "pytest/T01/GENERATOR", "signal_key": "Gen_RPM_Avg", "signal_type": "raw",
        "value": 1249.0, "unit": "RPM", "time": now,
    }


def test_get_current_value_raises_not_found(conn):
    _, reader_conn = conn
    with pytest.raises(NotFound):
        get_current_value(reader_conn, "pytest/does/not/exist", "Nope")


def test_get_historical_trend_short_range_uses_raw(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_readings (time, topic, signal_key, signal_type, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        (now, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1249.0),
    )
    seed_conn.commit()

    result = get_historical_trend(
        reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg", now - timedelta(minutes=30), now + timedelta(minutes=1)
    )
    assert result["source"] == "raw"
    assert len(result["points"]) == 1
    assert result["points"][0]["value"] == 1249.0


def test_get_historical_trend_long_range_uses_1h_aggregate(conn):
    _, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    result = get_historical_trend(
        reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg", now - timedelta(days=30), now
    )
    assert result["source"] == "1h"


def test_list_signals_filters_by_prefix_and_active_only(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, description, effective_since) VALUES (%s,%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", "RPM", None, now),
    )
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, description, effective_since, effective_until) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Old_Signal", "raw", "V", None, now - timedelta(days=1), now),
    )
    seed_conn.commit()

    results = list_signals(reader_conn, "pytest/T01")
    keys = [r["signal_key"] for r in results]
    assert "Gen_RPM_Avg" in keys
    assert "Old_Signal" not in keys


def test_list_active_alarms_returns_only_latest_snapshot(conn):
    seed_conn, reader_conn = conn
    older = datetime(2026, 9, 5, 11, 0, 0, tzinfo=timezone.utc)
    newest = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_events (time, topic, event_key, payload, signal_type) VALUES (%s,%s,%s,%s,%s)",
        (older, "pytest/T01/GENERATOR", "alarms", Jsonb({"signal": "Old_Alarm"}), "unknown"),
    )
    seed_conn.execute(
        "INSERT INTO silver_events (time, topic, event_key, payload, signal_type) VALUES (%s,%s,%s,%s,%s)",
        (newest, "pytest/T01/GENERATOR", "alarms", Jsonb({"signal": "Gen_RPM_Avg", "severity": "WARNING"}), "unknown"),
    )
    seed_conn.commit()

    results = list_active_alarms(reader_conn, "pytest/T01/GENERATOR")
    assert len(results) == 1
    assert results[0]["signal"] == "Gen_RPM_Avg"


def test_list_active_alarms_empty_when_none(conn):
    _, reader_conn = conn
    assert list_active_alarms(reader_conn, "pytest/no/alarms/here") == []
