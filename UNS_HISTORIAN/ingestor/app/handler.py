"""Wires message normalization + dedup + buffering together. Kept free of any
paho-mqtt or psycopg dependency so it can be unit tested without a live broker
or database.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, steps 4-5.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.buffer import FlushBuffer
from app.dedup import DedupCache
from app.normalize import parse_message


def handle_message(
    topic: str,
    raw: bytes,
    qos: int,
    retain: bool,
    arrival_time: datetime,
    cache: DedupCache,
    buffer: FlushBuffer,
) -> int:
    """Normalize `raw` into one or more readings, then dedup and buffer them
    as a single unit (the whole message), not reading-by-reading. Reading-by-
    reading dedup would let each element of a list payload overwrite a single
    per-topic cache slot, causing a replayed list to be re-inserted forever
    instead of collapsing to zero on an unchanged replay. Returns the number
    of rows appended to `buffer` (0 if the whole message was a duplicate)."""
    readings = parse_message(raw, arrival_time)
    message_comparable: Any = [
        reading.payload if reading.payload is not None else reading.raw_payload
        for reading in readings
    ]
    if not cache.should_store(topic, message_comparable):
        return 0
    for reading in readings:
        buffer.append((reading.time, topic, reading.payload, reading.raw_payload, qos, retain))
    return len(readings)
