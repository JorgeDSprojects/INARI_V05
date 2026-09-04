"""discover_live_topics only needs an object exposing async `scan_iter`
and `xrevrange` (the subset of redis.asyncio.Redis it calls), so it's
exercised here against a minimal in-memory fake instead of a live Redis
-- no live service needed for this logic."""
import json

import pytest

from app.services.live_topics import discover_live_topics


class FakeRedis:
    def __init__(self, streams: dict[str, list[tuple[str, dict]]]):
        self._streams = streams

    async def scan_iter(self, match: str, count: int = 100):
        for key in self._streams:
            yield key

    async def xrevrange(self, key: str, count: int = 1):
        return self._streams.get(key, [])[-count:][::-1]


@pytest.mark.asyncio
async def test_discover_live_topics_extracts_keys_from_latest_entry():
    fake = FakeRedis({
        "live:a/_informative": [("1-0", {"payload": json.dumps({"timestamp": "t", "Gen_RPM_Avg": 1300})})],
    })
    assert await discover_live_topics(fake) == [("a/_informative", "informative", ["Gen_RPM_Avg"])]


@pytest.mark.asyncio
async def test_discover_live_topics_skips_non_bridgeable_streams():
    fake = FakeRedis({"live:a/_descriptive": [("1-0", {"payload": "{}"})]})
    assert await discover_live_topics(fake) == []


@pytest.mark.asyncio
async def test_discover_live_topics_defaults_to_empty_keys_when_stream_is_empty():
    fake = FakeRedis({"live:a/_analytical": []})
    assert await discover_live_topics(fake) == [("a/_analytical", "analytical", [])]
