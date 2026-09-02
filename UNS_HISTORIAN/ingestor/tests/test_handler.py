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


def test_list_payload_splits_into_multiple_rows_on_first_delivery():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    raw = (
        b'[{"timestamp": "2026-09-02T13:20:16.748Z", "v": 1},'
        b' {"timestamp": "2026-09-02T13:20:17.748Z", "v": 1}]'
    )
    stored = handle_message("t/1", raw, 1, False, ARRIVAL, cache, buffer)
    assert stored == 2
    assert len(buffer.drain()) == 2


def test_retained_list_replay_is_fully_deduplicated_not_cycled():
    """Regression test for the fixed bug: a list message replayed (e.g. EMQX
    retained resend on reconnect) must be dropped as a whole, not re-inserted
    element-by-element forever because each element used to overwrite a
    single-value cache slot."""
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    raw = (
        b'[{"timestamp": "2026-09-02T13:20:16.748Z", "v": 1},'
        b' {"timestamp": "2026-09-02T13:20:17.748Z", "v": 2},'
        b' {"timestamp": "2026-09-02T13:20:18.748Z", "v": 3}]'
    )
    first = handle_message("t/1", raw, 1, True, ARRIVAL, cache, buffer)
    buffer.drain()
    second = handle_message("t/1", raw, 1, True, ARRIVAL, cache, buffer)
    third = handle_message("t/1", raw, 1, True, ARRIVAL, cache, buffer)
    assert first == 3
    assert second == 0
    assert third == 0
    assert buffer.drain() == []


def test_changed_list_payload_replaces_previous_message_entirely():
    cache = DedupCache()
    buffer = FlushBuffer(max_rows=10)
    raw1 = b'[{"timestamp": "2026-09-02T13:00:00Z", "v": 1}, {"timestamp": "2026-09-02T13:00:01Z", "v": 2}]'
    raw2 = b'[{"timestamp": "2026-09-02T13:05:00Z", "v": 9}, {"timestamp": "2026-09-02T13:05:01Z", "v": 9}]'
    handle_message("t/1", raw1, 1, True, ARRIVAL, cache, buffer)
    buffer.drain()
    stored = handle_message("t/1", raw2, 1, True, ARRIVAL, cache, buffer)
    assert stored == 2
    assert len(buffer.drain()) == 2
