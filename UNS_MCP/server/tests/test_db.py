import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app import db
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


def test_get_current_value_returns_a_real_float_not_a_decimal(conn):
    # value_numeric is NUMERIC, so psycopg hands back Decimal, which the MCP
    # SDK would JSON-serialize as the string "1203.5" instead of a number.
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", now, 1203.5),
    )
    seed_conn.commit()

    result = get_current_value(reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg")
    assert isinstance(result["value"], float)
    assert result["value"] == 1203.5


def test_get_current_value_prefers_the_catalog_signal_type(conn):
    # The catalog is authoritative; v.signal_type is only what the normalizer
    # inferred at write time. Disagreeing with list_signals about the same
    # signal is a bug.
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, effective_since) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "kpi", "RPM", now),
    )
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "unknown", now, 1249.0),
    )
    seed_conn.commit()

    assert get_current_value(reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg")["signal_type"] == "kpi"
    assert list_signals(reader_conn, "pytest/T01")[0]["signal_type"] == "kpi"


def test_get_current_value_falls_back_to_row_signal_type_without_a_catalog_entry(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Uncataloged", "raw", now, 7.0),
    )
    seed_conn.commit()

    assert get_current_value(reader_conn, "pytest/T01/GENERATOR", "Uncataloged")["signal_type"] == "raw"


def test_get_current_value_falls_back_to_text_when_numeric_is_null(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_text) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_State", "raw", now, "RUNNING"),
    )
    seed_conn.commit()

    assert get_current_value(reader_conn, "pytest/T01/GENERATOR", "Gen_State")["value"] == "RUNNING"


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
    assert isinstance(result["points"][0]["value"], float)
    assert result["truncated"] is False


def test_get_historical_trend_long_range_uses_1h_aggregate(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    # A catalog entry is enough to make the signal "known", so an empty
    # window is reported as empty rather than raising NotFound.
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, effective_since) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", "RPM", now),
    )
    seed_conn.commit()

    result = get_historical_trend(
        reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg", now - timedelta(days=30), now
    )
    assert result["source"] == "1h"


def test_get_historical_trend_raises_not_found_for_an_unknown_signal(conn):
    # A typo'd signal_key must not look like "no data in this window".
    _, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(NotFound):
        get_historical_trend(
            reader_conn, "pytest/T01/GENERATOR", "Typo_Signal", now - timedelta(minutes=30), now
        )
    # ...on the aggregate branch too, not just the raw one.
    with pytest.raises(NotFound):
        get_historical_trend(
            reader_conn, "pytest/T01/GENERATOR", "Typo_Signal", now - timedelta(days=30), now
        )


def test_get_historical_trend_returns_empty_for_a_known_signal_with_no_data_in_window(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO silver_readings (time, topic, signal_key, signal_type, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        (now, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1249.0),
    )
    seed_conn.execute(
        "INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric) VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", now, 1249.0),
    )
    seed_conn.commit()

    # A window a full day before the only reading: the signal exists, the
    # window is genuinely empty. That is success, not an error.
    result = get_historical_trend(
        reader_conn,
        "pytest/T01/GENERATOR",
        "Gen_RPM_Avg",
        now - timedelta(days=1, minutes=30),
        now - timedelta(days=1),
    )
    assert result["points"] == []
    assert result["truncated"] is False


def test_get_historical_trend_caps_the_number_of_returned_points(conn, monkeypatch):
    seed_conn, reader_conn = conn
    monkeypatch.setattr(db, "_MAX_POINTS", 3)
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        seed_conn.execute(
            "INSERT INTO silver_readings (time, topic, signal_key, signal_type, value_numeric) VALUES (%s,%s,%s,%s,%s)",
            (now - timedelta(minutes=i), "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1000.0 + i),
        )
    seed_conn.commit()

    result = get_historical_trend(
        reader_conn, "pytest/T01/GENERATOR", "Gen_RPM_Avg", now - timedelta(minutes=30), now
    )
    assert len(result["points"]) == 3
    assert result["truncated"] is True


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
