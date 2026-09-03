def is_informative_topic(topic: str) -> bool:
    return topic.rsplit("/", 1)[-1] == "_informative"
