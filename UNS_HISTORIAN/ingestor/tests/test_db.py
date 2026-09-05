import os
from datetime import datetime, timezone
from unittest.mock import patch

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


def test_insert_batch_commits_rows_durably(conn):
    """Verify that insert_batch commits rows durably to the database.
    This is critical because in the flush loop, if notify_silver_updates fails
    after insert_batch succeeds, the outer exception handlers must not re-queue
    rows that were already committed. This test confirms rows are durably
    committed by insert_batch and survive even if a subsequent operation fails."""
    now = datetime(2026, 9, 2, 12, 30, 0, tzinfo=timezone.utc)
    rows = [
        (now, "pytest/topic_durable_1", {"value": 1}, None, 1, False),
        (now, "pytest/topic_durable_2", {"value": 2}, None, 1, False),
    ]
    # Insert the rows (insert_batch commits them immediately)
    inserted = insert_batch(conn, rows)
    assert inserted == 2

    # Verify rows are committed by checking them in a fresh connection
    # (if they weren't committed, a new connection won't see them)
    verify_conn = psycopg.connect(DATABASE_URL)
    try:
        with verify_conn.cursor() as cur:
            cur.execute(
                "SELECT topic, payload FROM mqtt_messages WHERE topic LIKE 'pytest/topic_durable_%' ORDER BY topic"
            )
            results = cur.fetchall()
        assert len(results) == 2
        assert results[0] == ("pytest/topic_durable_1", {"value": 1})
        assert results[1] == ("pytest/topic_durable_2", {"value": 2})
    finally:
        verify_conn.close()
