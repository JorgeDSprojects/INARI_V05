"""Read-only queries against UNS_SILVER's tables, via the silver_reader role.

See docs/superpowers/specs/2026-09-05-uns-mcp-design.md, Section 2.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import psycopg


class NotFound(Exception):
    """Raised when a query finds no matching row for the given identifiers."""


def get_current_value(conn: psycopg.Connection, topic: str, signal_key: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.value_numeric, v.value_text, v.time, v.signal_type, c.unit
            FROM silver_latest_value v
            LEFT JOIN signal_catalog c
                ON c.topic = v.topic AND c.signal_key = v.signal_key AND c.effective_until IS NULL
            WHERE v.topic = %s AND v.signal_key = %s
            """,
            (topic, signal_key),
        )
        row = cur.fetchone()
    if row is None:
        raise NotFound(f"No current value for topic={topic!r} signal_key={signal_key!r}")
    value_numeric, value_text, time, signal_type, unit = row
    return {
        "topic": topic,
        "signal_key": signal_key,
        "signal_type": signal_type,
        "value": value_numeric if value_numeric is not None else value_text,
        "unit": unit,
        "time": time,
    }


def get_historical_trend(
    conn: psycopg.Connection, topic: str, signal_key: str, from_time: datetime, to_time: datetime
) -> dict[str, Any]:
    range_width = to_time - from_time
    with conn.cursor() as cur:
        if range_width <= timedelta(hours=1):
            cur.execute(
                """
                SELECT time, value_numeric, value_text FROM silver_readings
                WHERE topic = %s AND signal_key = %s AND time >= %s AND time <= %s
                ORDER BY time
                """,
                (topic, signal_key, from_time, to_time),
            )
            points = [
                {"time": r[0], "value": r[1] if r[1] is not None else r[2]} for r in cur.fetchall()
            ]
            return {"source": "raw", "points": points}

        table = "silver_readings_1m" if range_width <= timedelta(days=2) else "silver_readings_1h"
        cur.execute(
            f"""
            SELECT bucket, avg_value, min_value, max_value, sample_count FROM {table}
            WHERE topic = %s AND signal_key = %s AND bucket >= %s AND bucket <= %s
            ORDER BY bucket
            """,  # nosec: table is one of two fixed internal constants, never user input
            (topic, signal_key, from_time, to_time),
        )
        points = [
            {"bucket": r[0], "avg": r[1], "min": r[2], "max": r[3], "sample_count": r[4]}
            for r in cur.fetchall()
        ]
        return {"source": "1m" if table == "silver_readings_1m" else "1h", "points": points}


def list_signals(conn: psycopg.Connection, topic_prefix: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT topic, signal_key, signal_type, unit, description
            FROM signal_catalog
            WHERE topic LIKE %s AND effective_until IS NULL
            ORDER BY topic, signal_key
            """,
            (topic_prefix + "%",),
        )
        return [
            {"topic": r[0], "signal_key": r[1], "signal_type": r[2], "unit": r[3], "description": r[4]}
            for r in cur.fetchall()
        ]


def list_active_alarms(conn: psycopg.Connection, topic: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT payload FROM silver_events
            WHERE topic = %s AND event_key = 'alarms'
              AND time = (
                  SELECT MAX(time) FROM silver_events WHERE topic = %s AND event_key = 'alarms'
              )
            """,
            (topic, topic),
        )
        return [r[0] for r in cur.fetchall()]
