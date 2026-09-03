from app.services.ws_manager import TopicHub


def test_subscribe_tracks_client_under_topic():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.subscribe("client-2", "a/_informative")
    assert hub.subscribers_for("a/_informative") == {"client-1", "client-2"}


def test_topics_reflects_all_actively_subscribed_topics():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.subscribe("client-1", "b/_informative")
    assert hub.topics() == {"a/_informative", "b/_informative"}


def test_unsubscribe_all_removes_client_from_every_topic():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.subscribe("client-2", "a/_informative")
    hub.unsubscribe_all("client-1")
    assert hub.subscribers_for("a/_informative") == {"client-2"}


def test_unsubscribe_all_drops_topic_entirely_once_empty():
    hub = TopicHub()
    hub.subscribe("client-1", "a/_informative")
    hub.unsubscribe_all("client-1")
    assert "a/_informative" not in hub.topics()
