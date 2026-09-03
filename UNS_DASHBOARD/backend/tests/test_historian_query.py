from datetime import datetime, timedelta, timezone

from app.services.historian_query import choose_bucket_seconds, resolve_relative_range

NOW = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)


def test_choose_bucket_seconds_for_one_hour_range():
    assert choose_bucket_seconds(3600) == 5


def test_choose_bucket_seconds_for_one_month_range():
    assert choose_bucket_seconds(30 * 86400) == 3600


def test_resolve_relative_range_1h():
    start, end = resolve_relative_range("1h", NOW)
    assert end == NOW
    assert start == NOW - timedelta(hours=1)


def test_resolve_relative_range_30d():
    start, end = resolve_relative_range("30d", NOW)
    assert start == NOW - timedelta(days=30)


def test_resolve_relative_range_unknown_rule_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_relative_range("banana", NOW)
