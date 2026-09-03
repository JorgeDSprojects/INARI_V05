import json
from typing import Any


def stream_key(topic: str) -> str:
    return f"live:{topic}"


def build_fields(payload: dict[str, Any], arrival_iso: str) -> dict[str, str]:
    return {"time": arrival_iso, "payload": json.dumps(payload, ensure_ascii=False, default=str)}
