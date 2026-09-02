"""Normalize a raw MQTT message payload into one or more timestamped readings.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, step 4.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class Reading:
    time: datetime
    payload: Any
    raw_payload: str | None


def _extract_time(value: Any, arrival_time: datetime) -> datetime:
    """Use the object's own top-level 'timestamp' key when present and parseable."""
    if isinstance(value, dict) and isinstance(value.get("timestamp"), str):
        try:
            parsed = datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            return arrival_time
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return arrival_time


def parse_message(raw: bytes, arrival_time: datetime) -> list[Reading]:
    """Turn a raw MQTT payload into one or more Readings.

    - Empty payload -> one reading, payload=None, raw_payload=None.
    - Invalid JSON -> one reading, payload=None, raw_payload=<decoded text>.
    - JSON list -> one reading per element.
    - Any other JSON value (object, scalar) -> one reading.
    """
    if not raw:
        return [Reading(time=arrival_time, payload=None, raw_payload=None)]

    text = raw.decode("utf-8", errors="replace")

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return [Reading(time=arrival_time, payload=None, raw_payload=text)]

    if isinstance(parsed, list):
        return [
            Reading(time=_extract_time(item, arrival_time), payload=item, raw_payload=None)
            for item in parsed
        ]

    return [Reading(time=_extract_time(parsed, arrival_time), payload=parsed, raw_payload=None)]
