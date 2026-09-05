"""Postgres access for the Silver normalizer: watermark, bronze reads,
catalog reads/writes, readings/events inserts, latest-value upserts.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 2
(schema) and Section 3 (ingestion logic).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb

from app.catalog import SignalDefinition


@dataclass
class BronzeRow:
    id: int
    time: datetime
    topic: str
    payload: Any


def fetch_watermark(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT last_processed_id FROM silver_ingest_state WHERE id = 1")
        row = cur.fetchone()
    return row[0] if row else 0


def save_watermark(conn: psycopg.Connection, last_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO silver_ingest_state (id, last_processed_id) VALUES (1, %s)
            ON CONFLICT (id) DO UPDATE SET last_processed_id = EXCLUDED.last_processed_id
            """,
            (last_id,),
        )


def fetch_new_bronze_rows(historian_conn: psycopg.Connection, after_id: int, limit: int) -> list[BronzeRow]:
    with historian_conn.cursor() as cur:
        cur.execute(
            "SELECT id, time, topic, payload FROM mqtt_messages WHERE id > %s ORDER BY id LIMIT %s",
            (after_id, limit),
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
        return {
            row[0]: SignalDefinition(
                signal_key=row[0], signal_type=row[1], unit=row[2], data_type=row[3],
                range_min=row[4], range_max=row[5], thresholds=row[6], description=row[7],
                source_version=row[8],
            )
            for row in cur.fetchall()
        }


def apply_catalog_changes(
    conn: psycopg.Connection, topic: str, changed: list[SignalDefinition], observed_at: datetime
) -> None:
    with conn.cursor() as cur:
        for definition in changed:
            cur.execute(
                """
                UPDATE signal_catalog SET effective_until = %s
                WHERE topic = %s AND signal_key = %s AND effective_until IS NULL
                """,
                (observed_at, topic, definition.signal_key),
            )
            cur.execute(
                """
                INSERT INTO signal_catalog
                    (topic, signal_key, signal_type, unit, data_type, range_min, range_max,
                     thresholds, description, source_version, effective_since, effective_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
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
