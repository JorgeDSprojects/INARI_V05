from __future__ import annotations

from datetime import datetime, timedelta

_BUCKET_STEPS_SECONDS = [1, 5, 30, 60, 300, 3600, 86400]

RELATIVE_RULES: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def choose_bucket_seconds(range_seconds: float) -> int:
    """Target ~750 points across the range, snapped up to the next
    supported TimescaleDB bucket width."""
    target = range_seconds / 750
    for step in _BUCKET_STEPS_SECONDS:
        if step >= target:
            return step
    return _BUCKET_STEPS_SECONDS[-1]


def resolve_relative_range(rule: str, now: datetime) -> tuple[datetime, datetime]:
    if rule not in RELATIVE_RULES:
        raise ValueError(f"Unknown relative rule: {rule!r}")
    return now - RELATIVE_RULES[rule], now
