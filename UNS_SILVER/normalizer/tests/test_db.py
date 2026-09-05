import os
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.catalog import SignalDefinition
from app.db import (
    BronzeRow,
    apply_catalog_changes,
    fetch_active_definitions,
    fetch_new_bronze_rows,
    fetch_watermark,
    insert_events,
    insert_readings,
    save_watermark,
    upsert_latest_values,
)

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    connection.execute("DELETE FROM signal_catalog WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_readings WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_events WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_latest_value WHERE topic LIKE 'pytest/%'")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mqtt_messages (
            id BIGSERIAL, time TIMESTAMPTZ NOT NULL, topic TEXT NOT NULL, payload JSONB
        )
        """
    )
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    yield connection
    connection.rollback()
    connection.execute("DELETE FROM signal_catalog WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_readings WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_events WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM silver_latest_value WHERE topic LIKE 'pytest/%'")
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    connection.close()


def test_watermark_defaults_to_zero_then_roundtrips(conn):
    save_watermark(conn, 0)  # reset in case a prior failed run left state
    assert fetch_watermark(conn) == 0
    save_watermark(conn, 42)
    assert fetch_watermark(conn) == 42


def test_fetch_new_bronze_rows_respects_watermark_and_limit(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO mqtt_messages (time, topic, payload) VALUES (%s, %s, %s)",
            [(now, f"pytest/t{i}", Jsonb({"v": i})) for i in range(3)],
        )
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM mqtt_messages WHERE topic = 'pytest/t0'")
        first_id = cur.fetchone()[0]

    rows = fetch_new_bronze_rows(conn, after_id=first_id, limit=10)
    assert [r.topic for r in rows] == ["pytest/t1", "pytest/t2"]
    assert all(isinstance(r, BronzeRow) for r in rows)

    limited = fetch_new_bronze_rows(conn, after_id=first_id, limit=1)
    assert len(limited) == 1


def test_apply_and_fetch_active_definitions(conn):
    observed_at = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    definition = SignalDefinition(signal_key="Gen_RPM_Avg", signal_type="raw", unit="RPM", range_min=0, range_max=1700)
    apply_catalog_changes(conn, "pytest/T01/GENERATOR", [definition], observed_at)
    conn.commit()

    active = fetch_active_definitions(conn, "pytest/T01/GENERATOR")
    assert active["Gen_RPM_Avg"] == definition


def test_apply_catalog_changes_versions_instead_of_overwriting(conn):
    t1 = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 5, 13, 0, 0, tzinfo=timezone.utc)
    old = SignalDefinition(signal_key="Gen_RPM_Avg", signal_type="raw", range_max=1700)
    new = SignalDefinition(signal_key="Gen_RPM_Avg", signal_type="raw", range_max=1800)

    apply_catalog_changes(conn, "pytest/T01/GENERATOR", [old], t1)
    apply_catalog_changes(conn, "pytest/T01/GENERATOR", [new], t2)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT range_max, effective_since, effective_until FROM signal_catalog "
            "WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg' ORDER BY effective_since"
        )
        rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0] == (1700, t1, t2)
    assert rows[1][0] == 1800 and rows[1][2] is None


def test_insert_readings_and_upsert_latest_value(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    row = (now, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1249.0, None)
    assert insert_readings(conn, [row]) == 1
    upsert_latest_values(conn, [row])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT value_numeric FROM silver_latest_value WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'")
        assert cur.fetchone() == (1249.0,)


def test_upsert_latest_value_ignores_an_older_arrival(conn):
    older = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 9, 5, 13, 0, 0, tzinfo=timezone.utc)
    upsert_latest_values(conn, [(newer, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 2.0, None)])
    upsert_latest_values(conn, [(older, "pytest/T01/GENERATOR", "Gen_RPM_Avg", "raw", 1.0, None)])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT value_numeric FROM silver_latest_value WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'")
        assert cur.fetchone() == (2.0,)


def test_insert_events(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    row = (now, "pytest/T01/GENERATOR", "alarms", {"signal": "Gen_RPM_Avg", "severity": "WARNING"}, "unknown")
    assert insert_events(conn, [row]) == 1
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM silver_events WHERE topic = 'pytest/T01/GENERATOR' AND event_key = 'alarms'")
        assert cur.fetchone() == ({"signal": "Gen_RPM_Avg", "severity": "WARNING"},)


def test_insert_readings_with_empty_rows_is_a_noop(conn):
    assert insert_readings(conn, []) == 0
