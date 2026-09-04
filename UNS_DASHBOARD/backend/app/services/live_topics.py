"""Redis SCAN/XREVRANGE glue that discovers which topics the bridge is
currently mirroring into `live:<topic>` streams, for the live-mode
signal tree. Thin async I/O -- verified manually/live (see design spec
Section 1); the filtering/parsing logic is exercised here against a fake
Redis double, not a live one."""
from __future__ import annotations

import json

from app.services.signal_tree import topic_type_of

STREAM_PREFIX = "live:"


async def discover_live_topics(redis_client) -> list[tuple[str, str, list[str]]]:
    entries: list[tuple[str, str, list[str]]] = []
    async for key in redis_client.scan_iter(match=f"{STREAM_PREFIX}*", count=100):
        topic = key[len(STREAM_PREFIX):]
        topic_type = topic_type_of(topic)
        if topic_type is None:
            continue
        keys: list[str] = []
        latest = await redis_client.xrevrange(key, count=1)
        if latest:
            _entry_id, fields = latest[0]
            payload = json.loads(fields.get("payload", "{}"))
            if isinstance(payload, dict):
                keys = [k for k in payload.keys() if k != "timestamp"]
        entries.append((topic, topic_type, keys))
    return entries
