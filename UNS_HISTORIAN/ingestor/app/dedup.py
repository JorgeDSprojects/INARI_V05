"""In-memory last-value-per-topic cache used to suppress EMQX's retained-message
replay on reconnect without ever dropping genuine telemetry.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, step 5.
"""
from __future__ import annotations

from typing import Any

_MISSING = object()


class DedupCache:
    def __init__(self, initial: dict[str, Any] | None = None):
        self._last: dict[str, Any] = dict(initial or {})

    def should_store(self, topic: str, comparable: Any) -> bool:
        """Return True (and record `comparable` as the new last value) unless it
        is identical to the last stored value for `topic`."""
        previous = self._last.get(topic, _MISSING)
        if previous is not _MISSING and previous == comparable:
            return False
        self._last[topic] = comparable
        return True
