"""Orchestrates one processing cycle: fetch new bronze rows, route each by
topic suffix (catalog update vs. flatten-to-readings/events), and commit
everything — writes and the advanced watermark — atomically.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3.
"""
from __future__ import annotations

import logging

import psycopg

from app import catalog, db, flatten, topics
from app.config import Settings

logger = logging.getLogger("uns_silver.normalizer")

_VALUE_SUFFIXES = ("informative", "analytical")


def process_batch(
    historian_conn: psycopg.Connection, silver_conn: psycopg.Connection, settings: Settings
) -> int:
    last_id, last_time = db.fetch_watermark(silver_conn)
    rows = db.fetch_new_bronze_rows(historian_conn, last_id, last_time, settings.batch_size)
    if not rows:
        # fetch_watermark opened an implicit transaction on this non-autocommit
        # connection; returning without ending it would leave the connection
        # idle-in-transaction indefinitely on a quiet system, blocking autovacuum
        # and interfering with the compression/retention background jobs.
        silver_conn.rollback()
        return 0

    reading_rows: list[tuple] = []
    event_rows: list[tuple] = []
    max_id = last_id
    max_time = last_time
    unknown_count = 0

    for row in rows:
        base_topic, suffix = topics.classify_topic(row.topic)
        payload = row.payload if isinstance(row.payload, dict) else {}

        if suffix == "descriptive":
            incoming_defs = catalog.extract_definitions(payload)
            active = db.fetch_active_definitions(silver_conn, base_topic)
            changed = catalog.diff_definitions(active, incoming_defs)
            if changed:
                db.apply_catalog_changes(silver_conn, base_topic, changed, row.time)
                logger.info(
                    "Catalog updated: topic=%s, %d definition(s) changed (%s)",
                    base_topic, len(changed), ", ".join(d.signal_key for d in changed),
                )

        elif suffix in _VALUE_SUFFIXES:
            active = db.fetch_active_definitions(silver_conn, base_topic)
            flattened = flatten.flatten_payload(payload, settings.max_flatten_depth, settings.max_flatten_keys)
            if flattened.truncated:
                logger.warning("Payload truncated during flattening: topic=%s", row.topic)
            for value in flattened.values:
                signal_type = active[value.path].signal_type if value.path in active else "unknown"
                if signal_type == "unknown":
                    unknown_count += 1
                reading_rows.append(
                    (row.time, base_topic, value.path, signal_type, value.value_numeric, value.value_text)
                )
            for event in flattened.events:
                signal_type = active[event.event_key].signal_type if event.event_key in active else "unknown"
                if signal_type == "unknown":
                    unknown_count += 1
                event_rows.append((row.time, base_topic, event.event_key, event.payload, signal_type))

        max_id = row.id
        # `max(...)` rather than plain assignment: bronze `time` is the message's
        # own timestamp, so it is not monotonic with `id` and the last row of a
        # batch is not necessarily the latest one. The watermark time must only
        # ever move forward.
        max_time = max(max_time, row.time)

    if reading_rows:
        db.insert_readings(silver_conn, reading_rows)
        db.upsert_latest_values(silver_conn, reading_rows)
    if event_rows:
        db.insert_events(silver_conn, event_rows)

    db.save_watermark(silver_conn, max_id, max_time)
    silver_conn.commit()
    logger.info(
        "Batch processed: %d bronze row(s) -> %d reading(s), %d event(s)%s",
        len(rows), len(reading_rows), len(event_rows),
        f" ({unknown_count} unknown signal(s))" if unknown_count else "",
    )
    return len(rows)
