"""Parse `_descriptive` payloads into flat signal/KPI definitions, and diff
them against the currently active catalog to decide what needs a new
versioned row.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Key Decisions
("Topic structure") and the Global Constraints assumption about
`_descriptive.analytical`'s shape:

    "analytical": {
        "version": 2,
        "kpis": {
            "health_score": {"unit": null, "data_type": "float", "description": "...", "thresholds": {...}},
            ...
        }
    }

Raw physical signals keep their existing `signals` shape, with an optional
new `thresholds` sub-key per signal (previously lived in the now-retired
`_analytical.thresholds` map).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SignalDefinition:
    signal_key: str
    signal_type: str  # 'raw' | 'kpi'
    unit: str | None = None
    data_type: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    thresholds: dict | None = None
    description: str | None = None
    source_version: str | None = None


_COMPARABLE_FIELDS = (
    "signal_type", "unit", "data_type", "range_min", "range_max",
    "thresholds", "description", "source_version",
)


def extract_definitions(descriptive_payload: dict[str, Any]) -> list[SignalDefinition]:
    """Never raises on a malformed/missing section — returns whatever can be
    parsed, skipping entries that aren't the expected shape."""
    definitions: list[SignalDefinition] = []
    schema_version = descriptive_payload.get("schema_version")

    signals = descriptive_payload.get("signals")
    if isinstance(signals, dict):
        for key, spec in signals.items():
            if not isinstance(spec, dict):
                continue
            definitions.append(
                SignalDefinition(
                    signal_key=key,
                    signal_type="raw",
                    unit=spec.get("unit"),
                    data_type=spec.get("data_type"),
                    range_min=spec.get("range_min"),
                    range_max=spec.get("range_max"),
                    thresholds=spec.get("thresholds"),
                    description=spec.get("description"),
                    # Coerced to str to match the TEXT `source_version` column
                    # (and the KPI branch below): a publisher sending
                    # "schema_version": 1 must compare equal to a stored '1',
                    # otherwise every message would look like a version change.
                    source_version=str(schema_version) if schema_version is not None else None,
                )
            )

    analytical = descriptive_payload.get("analytical")
    if isinstance(analytical, dict):
        analytical_version = analytical.get("version")
        kpis = analytical.get("kpis")
        if isinstance(kpis, dict):
            # KNOWN INCONSISTENCY (documented, deliberately not worked around
            # here): a KPI is registered under its bare key (e.g.
            # "fleet_health_score"), but if the corresponding `_analytical`
            # value is a nested object, app/flatten.py emits dot-paths
            # ("fleet_health_score.value"), which will never match this bare-key
            # registration in batch.py's catalog lookup -- those readings land
            # as signal_type='unknown'. The real `_descriptive.analytical`
            # payload shape is still an unconfirmed assumption (see the plan's
            # Global Constraints), so no workaround is guessed here. Revisit
            # once the shape is confirmed with the team publishing it.
            for key, spec in kpis.items():
                if not isinstance(spec, dict):
                    continue
                definitions.append(
                    SignalDefinition(
                        signal_key=key,
                        signal_type="kpi",
                        unit=spec.get("unit"),
                        data_type=spec.get("data_type"),
                        range_min=spec.get("range_min"),
                        range_max=spec.get("range_max"),
                        thresholds=spec.get("thresholds"),
                        description=spec.get("description"),
                        source_version=str(analytical_version) if analytical_version is not None else None,
                    )
                )

    return definitions


def diff_definitions(
    active: dict[str, SignalDefinition], incoming: list[SignalDefinition]
) -> list[SignalDefinition]:
    """Return the subset of `incoming` that differs from (or has no) active
    definition for that signal_key — the ones that need a new versioned
    catalog row."""
    changed = []
    for definition in incoming:
        current = active.get(definition.signal_key)
        if current is None or _differs(current, definition):
            changed.append(definition)
    return changed


def _differs(current: SignalDefinition, incoming: SignalDefinition) -> bool:
    return any(getattr(current, f) != getattr(incoming, f) for f in _COMPARABLE_FIELDS)
