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


# --- Task 8 ---
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def query_history(
    session: AsyncSession,
    signals: list[tuple[str, str]],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Query one bucketed average per (topic, signal_key), grouping signals
    by topic to issue one query per unique topic, then merge all results by
    bucket timestamp into a single list of rows."""
    bucket_seconds = choose_bucket_seconds((end - start).total_seconds())
    by_topic: dict[str, list[str]] = defaultdict(list)
    for topic, key in signals:
        by_topic[topic].append(key)

    merged: dict[str, dict] = {}
    for topic, keys in by_topic.items():
        select_cols = ", ".join(f"avg((payload ->> :k{i})::numeric) AS v{i}" for i in range(len(keys)))
        params = {f"k{i}": key for i, key in enumerate(keys)}
        params.update({"topic": topic, "start": start, "end": end, "bucket": timedelta(seconds=bucket_seconds)})
        query = text(
            f"SELECT time_bucket(CAST(:bucket AS interval), time) AS bucket, {select_cols} "
            "FROM mqtt_messages WHERE topic = :topic AND time BETWEEN :start AND :end "
            "GROUP BY bucket ORDER BY bucket"
        )
        result = await session.execute(query, params)
        for row in result.mappings():
            bucket_iso = row["bucket"].isoformat()
            entry = merged.setdefault(bucket_iso, {"time": bucket_iso})
            for i, key in enumerate(keys):
                value = row[f"v{i}"]
                entry[key] = float(value) if value is not None else None

    return [merged[k] for k in sorted(merged)]
