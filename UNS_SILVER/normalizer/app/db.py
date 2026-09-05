"""Postgres access for the Silver normalizer: watermark, bronze reads,
catalog reads/writes, readings/events inserts, latest-value upserts.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 2
(schema) and Section 3 (ingestion logic).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb

from app.catalog import SignalDefinition

# How far BEHIND the stored watermark time the bronze scan still looks.
#
# `mqtt_messages.id` is assigned at INSERT time, but `mqtt_messages.time` comes
# from the message's own `timestamp` field when the publisher provides one (see
# UNS_HISTORIAN/ingestor/app/normalize.py::_extract_time), so `time` is NOT
# monotonic with `id`: a row inserted later can carry an earlier timestamp.
# Measured on the live historian (66.5k rows): 82% of rows carry a `time` behind
# the running maximum, with a worst-case lateness of 21h53m and none beyond one
# day.
#
# A bare `time >= last_processed_time` predicate would therefore silently and
# permanently skip those rows. This lookback keeps the predicate (so TimescaleDB
# can still exclude old chunks, which is the whole point of tracking a time
# watermark) while tolerating out-of-order arrival up to the margin below.
# 7 days matches `mqtt_messages`' chunk interval, so the slack costs at most one
# extra chunk regardless of how much total history the hypertable accumulates.
_BRONZE_SCAN_LOOKBACK = "7 days"


@dataclass
class BronzeRow:
    id: int
    time: datetime
    topic: str
    payload: Any


def fetch_watermark(conn: psycopg.Connection) -> tuple[int, datetime]:
    with conn.cursor() as cur:
        cur.execute("SELECT last_processed_id, last_processed_time FROM silver_ingest_state WHERE id = 1")
        row = cur.fetchone()
    if row:
        return row[0], row[1]
    return 0, datetime.min.replace(tzinfo=timezone.utc)


def save_watermark(conn: psycopg.Connection, last_id: int, last_time: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO silver_ingest_state (id, last_processed_id, last_processed_time) VALUES (1, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                last_processed_id = EXCLUDED.last_processed_id,
                last_processed_time = EXCLUDED.last_processed_time
            """,
            (last_id, last_time),
        )


def fetch_new_bronze_rows(
    historian_conn: psycopg.Connection, after_id: int, after_time: datetime, limit: int
) -> list[BronzeRow]:
    """`id > after_id` is the correctness predicate; the `time >=` predicate is
    purely a chunk-exclusion hint so the scan cost does not grow with the total
    number of `mqtt_messages` chunks. See `_BRONZE_SCAN_LOOKBACK` for why the
    time bound is deliberately slack rather than exactly `after_time`."""
    with historian_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, time, topic, payload
            FROM mqtt_messages
            WHERE time >= %s::timestamptz - %s::interval AND id > %s
            ORDER BY id
            LIMIT %s
            """,
            (after_time, _BRONZE_SCAN_LOOKBACK, after_id, limit),
        )
        return [BronzeRow(id=r[0], time=r[1], topic=r[2], payload=r[3]) for r in cur.fetchall()]


def fetch_active_definitions(conn: psycopg.Connection, topic: str) -> dict[str, SignalDefinition]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT signal_key, signal_type, unit, data_type, range_min, range_max,
                   thresholds, description, source_version
            FROM signal_catalog
            WHERE topic = %s AND effective_until IS NULL
            """,
            (topic,),
        )
        # range_min/range_max are NUMERIC, so psycopg hands them back as Decimal.
        # SignalDefinition values parsed from JSON are native float/int, and
        # Decimal('0.1') == 0.1 is False -- without this cast every float-valued
        # range would look "changed" to catalog.diff_definitions on every single
        # _descriptive message, closing and reopening a catalog row each time.
        return {
            row[0]: SignalDefinition(
                signal_key=row[0], signal_type=row[1], unit=row[2], data_type=row[3],
                range_min=float(row[4]) if row[4] is not None else None,
                range_max=float(row[5]) if row[5] is not None else None,
                thresholds=row[6], description=row[7],
                source_version=row[8],
            )
            for row in cur.fetchall()
        }


def apply_catalog_changes(
    conn: psycopg.Connection, topic: str, changed: list[SignalDefinition], observed_at: datetime
) -> None:
    """NOTE: the INSERT below is an upsert specifically so that two `_descriptive`
    messages for the same topic bearing an identical bronze `time` (used as
    `effective_since`) cannot raise a UNIQUE (topic, signal_key, effective_since)
    violation -- such a violation would abort the batch, block the watermark from
    advancing, and make the pipeline refetch the same failing rows forever.

    The `effective_since < observed_at` guard on the closing UPDATE is part of the
    same mitigation: without it the second same-timestamp message would close the
    row the first one just opened (a zero-length version), and the upsert -- which
    never reopens `effective_until` -- would leave the signal with no active
    catalog row at all.

    Full poison-pill row-by-row isolation for OTHER failure classes (e.g. a
    genuinely malformed row raising some different exception) is NOT implemented
    here; it remains a deferred future hardening item, tracked in
    docs/superpowers/specs/2026-09-05-uns-silver-design.md."""
    with conn.cursor() as cur:
        for definition in changed:
            cur.execute(
                """
                UPDATE signal_catalog SET effective_until = %s
                WHERE topic = %s AND signal_key = %s AND effective_until IS NULL
                  AND effective_since < %s
                """,
                (observed_at, topic, definition.signal_key, observed_at),
            )
            cur.execute(
                """
                INSERT INTO signal_catalog
                    (topic, signal_key, signal_type, unit, data_type, range_min, range_max,
                     thresholds, description, source_version, effective_since, effective_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                ON CONFLICT (topic, signal_key, effective_since) DO UPDATE SET
                    signal_type = EXCLUDED.signal_type,
                    unit = EXCLUDED.unit,
                    data_type = EXCLUDED.data_type,
                    range_min = EXCLUDED.range_min,
                    range_max = EXCLUDED.range_max,
                    thresholds = EXCLUDED.thresholds,
                    description = EXCLUDED.description,
                    source_version = EXCLUDED.source_version
                """,
                (
                    topic, definition.signal_key, definition.signal_type, definition.unit,
                    definition.data_type, definition.range_min, definition.range_max,
                    Jsonb(definition.thresholds) if definition.thresholds is not None else None,
                    definition.description, definition.source_version, observed_at,
                ),
            )


def insert_readings(conn: psycopg.Connection, rows: Iterable[tuple]) -> int:
    """Each row: (time, topic, signal_key, signal_type, value_numeric, value_text)."""
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver_readings (time, topic, signal_key, signal_type, value_numeric, value_text)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def insert_events(conn: psycopg.Connection, rows: Iterable[tuple]) -> int:
    """Each row: (time, topic, event_key, payload, signal_type)."""
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver_events (time, topic, event_key, payload, signal_type)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(t, topic, key, Jsonb(payload), st) for (t, topic, key, payload, st) in rows],
        )
    return len(rows)


def upsert_latest_values(conn: psycopg.Connection, rows: Iterable[tuple]) -> None:
    """Same row shape as `insert_readings`: (time, topic, signal_key, signal_type,
    value_numeric, value_text) — callers can pass the same list to both."""
    rows = list(rows)
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver_latest_value (topic, signal_key, signal_type, time, value_numeric, value_text)
            VALUES (%(topic)s, %(signal_key)s, %(signal_type)s, %(time)s, %(value_numeric)s, %(value_text)s)
            ON CONFLICT (topic, signal_key) DO UPDATE SET
                signal_type = EXCLUDED.signal_type,
                time = EXCLUDED.time,
                value_numeric = EXCLUDED.value_numeric,
                value_text = EXCLUDED.value_text
            WHERE EXCLUDED.time >= silver_latest_value.time
            """,
            [
                {"time": t, "topic": topic, "signal_key": key, "signal_type": st,
                 "value_numeric": vn, "value_text": vt}
                for (t, topic, key, st, vn, vt) in rows
            ],
        )
