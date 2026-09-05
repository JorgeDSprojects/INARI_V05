import os
from datetime import datetime, timezone

import psycopg
import pytest

from app.db import insert_batch, load_last_values, notify_silver_updates

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL)
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    yield connection
    connection.execute("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'")
    connection.commit()
    connection.close()


def test_insert_batch_writes_rows(conn):
    now = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    rows = [(now, "pytest/topic1", {"value": 1}, None, 1, True)]
    inserted = insert_batch(conn, rows)
    assert inserted == 1
    with conn.cursor() as cur:
        cur.execute("SELECT topic, payload FROM mqtt_messages WHERE topic = 'pytest/topic1'")
        result = cur.fetchone()
    assert result == ("pytest/topic1", {"value": 1})


def test_load_last_values_returns_most_recent_payload_per_topic(conn):
    t1 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 2, 12, 0, 5, tzinfo=timezone.utc)
    insert_batch(
        conn,
        [
            (t1, "pytest/topic2", {"value": 1}, None, 1, False),
            (t2, "pytest/topic2", {"value": 2}, None, 1, False),
        ],
    )
    last_values = load_last_values(conn)
    assert last_values["pytest/topic2"] == {"value": 2}


def test_insert_batch_with_empty_rows_is_a_noop(conn):
    assert insert_batch(conn, []) == 0


def test_notify_silver_updates_is_received_by_a_listener(conn):
    listener = psycopg.connect(DATABASE_URL, autocommit=True)
    try:
        listener.execute("LISTEN silver_updates")
        notify_silver_updates(conn)
        received = list(listener.notifies(timeout=2))
        assert any(n.channel == "silver_updates" for n in received)
    finally:
        listener.close()
