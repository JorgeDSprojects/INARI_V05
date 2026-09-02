"""Thread-safe row buffer drained periodically by the flush loop.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3, step 6.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any


class FlushBuffer:
    def __init__(self, max_rows: int):
        self._lock = threading.Lock()
        self._rows: deque[Any] = deque()
        self._max_rows = max_rows
        self._dropped = 0

    def append(self, row: Any) -> None:
        with self._lock:
            if len(self._rows) >= self._max_rows:
                self._rows.popleft()
                self._dropped += 1
            self._rows.append(row)

    def __len__(self) -> int:
        with self._lock:
            return len(self._rows)

    def drain(self) -> list[Any]:
        with self._lock:
            rows = list(self._rows)
            self._rows.clear()
            return rows

    def pop_dropped_count(self) -> int:
        with self._lock:
            n = self._dropped
            self._dropped = 0
            return n
