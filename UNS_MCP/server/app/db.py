"""Read-only queries against UNS_SILVER's tables, via the silver_reader role.

See docs/superpowers/specs/2026-09-05-uns-mcp-design.md, Section 2.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import psycopg


_MAX_POINTS = 1000
"""Hard cap on points returned by get_historical_trend. A wide range at fine
granularity (2 days of 1-minute buckets is ~2,880 points) would otherwise
push tens of KB through the model's context for one tool call."""


class NotFound(Exception):
    """Raised when a query finds no matching row for the given identifiers."""


def _to_float(value, ndigits: int | None = None):
    """Coerce psycopg's Decimal (from Postgres NUMERIC) to a real float.

    Without this, the MCP SDK JSON-serializes Decimal as a string, so clients
    see "value": "1203.5" instead of the number the spec documents. `ndigits`
    trims repeating-decimal noise from SQL avg() ("1119.6666666666666667").
    """
    if value is None:
        return None
    result = float(value)
    return round(result, ndigits) if ndigits is not None else result


def get_current_value(conn: psycopg.Connection, topic: str, signal_key: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.value_numeric, v.value_text, v.time, COALESCE(c.signal_type, v.signal_type), c.unit
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
    numeric = _to_float(value_numeric)
    return {
        "topic": topic,
        "signal_key": signal_key,
        # The catalog is authoritative when it has an entry; v.signal_type is
        # only whatever the normalizer inferred at write time, so preferring
        # it would let get_current_value and list_signals disagree.
        "signal_type": signal_type,
        "value": numeric if numeric is not None else value_text,
        "unit": unit,
        "time": time,
    }


def _signal_is_known(conn: psycopg.Connection, topic: str, signal_key: str) -> bool:
    """Has the system ever heard of this signal at all?

    Distinguishes "no data in the requested window" (a legitimate empty
    result) from "you typo'd the signal_key" (which must not look like
    success). A signal counts as known if it has a latest value or an active
    catalog entry.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM silver_latest_value WHERE topic = %s AND signal_key = %s
            UNION
            SELECT 1 FROM signal_catalog WHERE topic = %s AND signal_key = %s AND effective_until IS NULL
            """,
            (topic, signal_key, topic, signal_key),
        )
        return cur.fetchone() is not None


def get_historical_trend(
    conn: psycopg.Connection, topic: str, signal_key: str, from_time: datetime, to_time: datetime
) -> dict[str, Any]:
    range_width = to_time - from_time
    with conn.cursor() as cur:
        if range_width <= timedelta(hours=1):
            source = "raw"
            cur.execute(
                """
                SELECT time, value_numeric, value_text FROM silver_readings
                WHERE topic = %s AND signal_key = %s AND time >= %s AND time <= %s
                ORDER BY time
                LIMIT %s
                """,
                (topic, signal_key, from_time, to_time, _MAX_POINTS + 1),
            )
            rows = cur.fetchall()
            truncated = len(rows) > _MAX_POINTS
            points = [
                {"time": r[0], "value": _to_float(r[1]) if r[1] is not None else r[2]}
                for r in rows[:_MAX_POINTS]
            ]
        else:
            table = "silver_readings_1m" if range_width <= timedelta(days=2) else "silver_readings_1h"
            source = "1m" if table == "silver_readings_1m" else "1h"
            # GROUP BY bucket, aggregating across signal_type: the continuous
            # aggregates group by (topic, signal_key, signal_type, bucket), so
            # a signal whose signal_type ever changes would otherwise yield
            # duplicate rows for the same bucket.
            cur.execute(
                f"""
                SELECT bucket, avg(avg_value), min(min_value), max(max_value), sum(sample_count)
                FROM {table}
                WHERE topic = %s AND signal_key = %s AND bucket >= %s AND bucket <= %s
                GROUP BY bucket
                ORDER BY bucket
                LIMIT %s
                """,  # nosec: table is one of two fixed internal constants, never user input
                (topic, signal_key, from_time, to_time, _MAX_POINTS + 1),
            )
            rows = cur.fetchall()
            truncated = len(rows) > _MAX_POINTS
            points = [
                {
                    "bucket": r[0],
                    "avg": _to_float(r[1], ndigits=4),
                    "min": _to_float(r[2]),
                    "max": _to_float(r[3]),
                    # sum(bigint) comes back from Postgres as NUMERIC, i.e. a
                    # Decimal, which would serialize as a string like the
                    # value fields above; a sample count is always an integer.
                    "sample_count": int(r[4]) if r[4] is not None else None,
                }
                for r in rows[:_MAX_POINTS]
            ]

    if not points and not _signal_is_known(conn, topic, signal_key):
        raise NotFound(f"No signal known for topic={topic!r} signal_key={signal_key!r}")

    return {"source": source, "points": points, "truncated": truncated}


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
