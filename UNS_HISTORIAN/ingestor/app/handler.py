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
    """Normalize `raw` into readings, drop duplicates, buffer the rest for
    insertion. Returns the number of rows appended to `buffer`."""
    stored = 0
    for reading in parse_message(raw, arrival_time):
        comparable: Any = reading.payload if reading.payload is not None else reading.raw_payload
        if not cache.should_store(topic, comparable):
            continue
        buffer.append((reading.time, topic, reading.payload, reading.raw_payload, qos, retain))
        stored += 1
    return stored
