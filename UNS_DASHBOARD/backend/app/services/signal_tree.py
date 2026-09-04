"""Pure topic-path -> nested-tree builder shared by the historical
(Historian-backed) and live (Redis-backed) signal-tree endpoints. Has no
I/O and is fully unit tested; see design spec Section 1."""
from __future__ import annotations

_BRIDGEABLE_SUFFIXES = {"_informative": "informative", "_analytical": "analytical"}

TopicEntry = tuple[str, str, list[str]]


def topic_type_of(topic: str) -> str | None:
    return _BRIDGEABLE_SUFFIXES.get(topic.rsplit("/", 1)[-1])


def build_tree(entries: list[TopicEntry]) -> list[dict]:
    root: dict = {"children": {}}

    for topic, topic_type, keys in entries:
        node = root
        for segment in topic.split("/"):
            node = node["children"].setdefault(segment, {"children": {}})
        node["leaf"] = {"topic": topic, "topic_type": topic_type, "keys": keys}

    def to_list(node: dict) -> list[dict]:
        result = []
        for segment, child in sorted(node["children"].items()):
            entry: dict = {"segment": segment, "children": to_list(child)}
            if "leaf" in child:
                entry["leaf"] = child["leaf"]
            result.append(entry)
        return result

    return to_list(root)
