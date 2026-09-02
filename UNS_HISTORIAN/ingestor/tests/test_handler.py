from datetime import datetime, timezone

from app.buffer import FlushBuffer
from app.dedup import DedupCache
from app.handler import handle_message

ARRIVAL = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_new_reading_is_buffered():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    stored = handle_message("t/1", b'{"value": 1}', 1, True, ARRIVAL, cache, buffer)
    assert stored == 1
    rows = buffer.drain()
    assert rows == [(ARRIVAL, "t/1", {"value": 1}, None, 1, True)]


def test_duplicate_reading_is_not_buffered():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    handle_message("t/1", b'{"value": 1}', 1, True, ARRIVAL, cache, buffer)
    buffer.drain()
    stored = handle_message("t/1", b'{"value": 1}', 1, True, ARRIVAL, cache, buffer)
    assert stored == 0
    assert buffer.drain() == []


def test_list_payload_splits_and_dedupes_independently():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    raw = (
        b'[{"timestamp": "2026-09-02T13:20:16.748Z", "v": 1},'
        b' {"timestamp": "2026-09-02T13:20:17.748Z", "v": 1}]'
    )
    stored = handle_message("t/1", raw, 1, False, ARRIVAL, cache, buffer)
    assert stored == 2  # different timestamps -> never deduped against each other
    assert len(buffer.drain()) == 2
