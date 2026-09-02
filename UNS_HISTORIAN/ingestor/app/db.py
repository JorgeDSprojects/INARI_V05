"""Postgres access: startup cache warm-up and batched inserts.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, steps 2 and 6.
"""
from __future__ import annotations

from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb


def load_last_values(conn: psycopg.Connection) -> dict[str, Any]:
    """Seed the dedup cache: last payload (or raw_payload) stored per topic."""
    query = """
        SELECT DISTINCT ON (topic) topic, payload, raw_payload
        FROM mqtt_messages
        ORDER BY topic, time DESC
    """
    result: dict[str, Any] = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for topic, payload, raw_payload in cur.fetchall():
            result[topic] = payload if payload is not None else raw_payload
    return result


def insert_batch(conn: psycopg.Connection, rows: Iterable[tuple]) -> int:
    """Batch-insert (time, topic, payload, raw_payload, qos, retain) rows.
    Returns the number of rows inserted."""
    rows = list(rows)
    if not rows:
        return 0
    params = [
        (time, topic, Jsonb(payload) if payload is not None else None, raw_payload, qos, retain)
        for time, topic, payload, raw_payload, qos, retain in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO mqtt_messages (time, topic, payload, raw_payload, qos, retain)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            params,
        )
    conn.commit()
    return len(rows)
