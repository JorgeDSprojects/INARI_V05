import os
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.batch import process_batch
from app.config import load_settings
from app.db import fetch_watermark, save_watermark

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)

SETTINGS = load_settings({"NORMALIZER_BATCH_SIZE": "10", "MAX_FLATTEN_DEPTH": "6", "MAX_FLATTEN_KEYS_PER_MESSAGE": "500"})


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mqtt_messages (
            id BIGSERIAL, time TIMESTAMPTZ NOT NULL, topic TEXT NOT NULL, payload JSONB
        )
        """
    )
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value", "mqtt_messages"):
        connection.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    save_watermark(connection, 0)
    connection.commit()
    yield connection
    connection.rollback()
    for table in ("signal_catalog", "silver_readings", "silver_events", "silver_latest_value", "mqtt_messages"):
        connection.execute(f"DELETE FROM {table} WHERE topic LIKE 'pytest/%'")
    connection.commit()
    connection.close()


def _insert_bronze(conn, topic: str, payload: dict, time: datetime) -> None:
    conn.execute(
        "INSERT INTO mqtt_messages (time, topic, payload) VALUES (%s, %s, %s)",
        (time, topic, Jsonb(payload)),
    )
    conn.commit()


def test_no_new_rows_returns_zero(conn):
    assert process_batch(conn, conn, SETTINGS) == 0


def test_descriptive_message_populates_catalog(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(
        conn, "pytest/T01/GENERATOR/_descriptive",
        {"schema_version": "1.0.0", "signals": {"Gen_RPM_Avg": {"unit": "RPM", "range_max": 1700}}},
        now,
    )
    processed = process_batch(conn, conn, SETTINGS)
    assert processed == 1
    with conn.cursor() as cur:
        cur.execute(
            "SELECT signal_type, unit FROM signal_catalog WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'"
        )
        assert cur.fetchone() == ("raw", "RPM")


def test_informative_message_produces_reading_tagged_from_catalog(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(
        conn, "pytest/T01/GENERATOR/_descriptive",
        {"schema_version": "1.0.0", "signals": {"Gen_RPM_Avg": {"unit": "RPM"}}},
        now,
    )
    _insert_bronze(conn, "pytest/T01/GENERATOR/_informative", {"timestamp": "2026-09-05T12:00:05Z", "Gen_RPM_Avg": 1249.0}, now)

    processed = process_batch(conn, conn, SETTINGS)
    assert processed == 2

    with conn.cursor() as cur:
        cur.execute(
            "SELECT signal_type, value_numeric FROM silver_readings WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'"
        )
        assert cur.fetchone() == ("raw", 1249.0)
        cur.execute(
            "SELECT value_numeric FROM silver_latest_value WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Gen_RPM_Avg'"
        )
        assert cur.fetchone() == (1249.0,)


def test_uncataloged_signal_is_tagged_unknown_not_dropped(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(conn, "pytest/T01/GENERATOR/_informative", {"Mystery_Signal": 42.0}, now)
    process_batch(conn, conn, SETTINGS)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT signal_type FROM silver_readings WHERE topic = 'pytest/T01/GENERATOR' AND signal_key = 'Mystery_Signal'"
        )
        assert cur.fetchone() == ("unknown",)


def test_analytical_array_of_objects_becomes_event(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "status": "WARNING",
        "alarms": [{"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4}],
    }
    _insert_bronze(conn, "pytest/T01/GENERATOR/_analytical", payload, now)
    process_batch(conn, conn, SETTINGS)
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM silver_events WHERE topic = 'pytest/T01/GENERATOR' AND event_key = 'alarms'")
        assert cur.fetchone() == ({"signal": "Gen_RPM_Avg", "severity": "WARNING", "current_value": 1427.4},)


def test_watermark_advances_and_reprocessing_is_a_noop(conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    _insert_bronze(conn, "pytest/T01/GENERATOR/_informative", {"Gen_RPM_Avg": 1.0}, now)
    process_batch(conn, conn, SETTINGS)
    watermark_after_first = fetch_watermark(conn)
    assert process_batch(conn, conn, SETTINGS) == 0
    assert fetch_watermark(conn) == watermark_after_first
