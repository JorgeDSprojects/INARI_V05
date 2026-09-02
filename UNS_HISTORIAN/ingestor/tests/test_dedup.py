from app.dedup import DedupCache


def test_new_topic_is_always_stored():
    cache = DedupCache()
    assert cache.should_store("t/1", {"a": 1}) is True


def test_identical_payload_is_skipped():
    cache = DedupCache()
    cache.should_store("t/1", {"a": 1})
    assert cache.should_store("t/1", {"a": 1}) is False


def test_changed_payload_is_stored():
    cache = DedupCache()
    cache.should_store("t/1", {"a": 1})
    assert cache.should_store("t/1", {"a": 2}) is True


def test_repeated_none_is_skipped():
    cache = DedupCache()
    cache.should_store("t/1", None)
    assert cache.should_store("t/1", None) is False


def test_seeded_from_initial_dict_deduplicates_first_message():
    cache = DedupCache(initial={"t/1": {"a": 1}})
    assert cache.should_store("t/1", {"a": 1}) is False


def test_different_topics_are_independent():
    cache = DedupCache()
    cache.should_store("t/1", {"a": 1})
    assert cache.should_store("t/2", {"a": 1}) is True
