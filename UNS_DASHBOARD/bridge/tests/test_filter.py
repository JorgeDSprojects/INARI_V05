from app.filter import is_informative_topic


def test_informative_suffix_matches():
    assert is_informative_topic("Enterprise/Site/Area/_informative") is True


def test_descriptive_suffix_does_not_match():
    assert is_informative_topic("Enterprise/Site/Area/_descriptive") is False


def test_topic_without_suffix_does_not_match():
    assert is_informative_topic("Enterprise/Site/Area") is False
