"""Generic recursive flattener for `_informative`/`_analytical` value
payloads. Deliberately not a per-shape parser: it works uniformly across
every ISA-95 hierarchy level and every publisher, because analytical
payloads are not a stable project-wide schema (asset-level alarm status,
fleet-level business targets, site-level regulatory compliance all differ).

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3,
second bullet ("generic recursive flatten").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# The message envelope's own event time is already captured by the bronze
# row's `time` column (reused verbatim for every row Silver produces from
# that message) — flattening it again as a signal would just be noise.
_ENVELOPE_KEYS_SKIPPED_AT_ROOT = {"timestamp"}


@dataclass
class FlatValue:
    path: str
    value_numeric: float | None
    value_text: str | None


@dataclass
class FlatEvent:
    event_key: str
    payload: dict


@dataclass
class FlattenResult:
    values: list[FlatValue] = field(default_factory=list)
    events: list[FlatEvent] = field(default_factory=list)
    truncated: bool = False


def flatten_payload(payload: Any, max_depth: int, max_keys: int) -> FlattenResult:
    result = FlattenResult()
    if not isinstance(payload, dict):
        return result
    _walk(payload, path=None, depth=0, max_depth=max_depth, max_keys=max_keys, result=result, is_root=True)
    return result


def _walk(
    node: Any,
    path: str | None,
    depth: int,
    max_depth: int,
    max_keys: int,
    result: FlattenResult,
    is_root: bool = False,
) -> None:
    if len(result.values) + len(result.events) >= max_keys:
        result.truncated = True
        return

    if isinstance(node, dict):
        if depth >= max_depth:
            result.truncated = True
            return
        for key, child in node.items():
            if is_root and key in _ENVELOPE_KEYS_SKIPPED_AT_ROOT:
                continue
            child_path = key if path is None else f"{path}.{key}"
            _walk(child, child_path, depth + 1, max_depth, max_keys, result)
        return

    if isinstance(node, list):
        if path is None:
            return  # a bare top-level array has no key to attach a path to
        if node and all(isinstance(item, dict) for item in node):
            for item in node:
                if len(result.values) + len(result.events) >= max_keys:
                    result.truncated = True
                    return
                result.events.append(FlatEvent(event_key=path, payload=item))
        elif node:
            result.values.append(FlatValue(path=path, value_numeric=None, value_text=json.dumps(node)))
        return

    if path is None:
        return  # a bare top-level scalar has no key (shouldn't occur for a JSON object payload)

    if isinstance(node, bool):
        result.values.append(FlatValue(path=path, value_numeric=None, value_text=str(node)))
    elif isinstance(node, (int, float)):
        result.values.append(FlatValue(path=path, value_numeric=float(node), value_text=None))
    elif node is None:
        result.values.append(FlatValue(path=path, value_numeric=None, value_text=None))
    else:
        result.values.append(FlatValue(path=path, value_numeric=None, value_text=str(node)))
