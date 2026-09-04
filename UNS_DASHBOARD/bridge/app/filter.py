_BRIDGEABLE_SUFFIXES = {"_informative", "_analytical"}


def is_bridgeable_topic(topic: str) -> bool:
    return topic.rsplit("/", 1)[-1] in _BRIDGEABLE_SUFFIXES
