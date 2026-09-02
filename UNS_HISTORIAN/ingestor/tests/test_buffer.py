from app.buffer import FlushBuffer


def test_append_and_drain_returns_rows_in_order():
    buf = FlushBuffer(max_rows=10)
    buf.append("a")
    buf.append("b")
    assert buf.drain() == ["a", "b"]


def test_drain_empties_the_buffer():
    buf = FlushBuffer(max_rows=10)
    buf.append("a")
    buf.drain()
    assert buf.drain() == []
    assert len(buf) == 0


def test_exceeding_max_rows_drops_oldest_and_counts_it():
    buf = FlushBuffer(max_rows=2)
    buf.append("a")
    buf.append("b")
    buf.append("c")
    assert buf.drain() == ["b", "c"]
    assert buf.pop_dropped_count() == 1


def test_pop_dropped_count_resets_to_zero():
    buf = FlushBuffer(max_rows=1)
    buf.append("a")
    buf.append("b")
    buf.pop_dropped_count()
    assert buf.pop_dropped_count() == 0
