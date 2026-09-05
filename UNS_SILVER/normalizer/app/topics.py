"""Classify an MQTT topic by its UNS suffix and strip it to the base
ISA-95 node topic that catalog entries and readings/events are keyed on.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3.
"""
from __future__ import annotations

_SUFFIXES = {
    "/_descriptive": "descriptive",
    "/_informative": "informative",
    "/_analytical": "analytical",
}


def classify_topic(topic: str) -> tuple[str, str]:
    for suffix, name in _SUFFIXES.items():
        if topic.endswith(suffix):
            return topic[: -len(suffix)], name
    return topic, "other"
