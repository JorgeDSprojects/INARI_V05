from __future__ import annotations

from typing import Any

import jsonschema
import jsonschema.exceptions


def validate_payload(schema: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate payload against a JSON Schema. Returns (valid, error_messages)."""
    if not schema:
        return True, []
    try:
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if errors:
            return False, [e.message for e in errors]
        return True, []
    except jsonschema.exceptions.SchemaError as exc:
        return False, [f"Invalid schema: {exc.message}"]
