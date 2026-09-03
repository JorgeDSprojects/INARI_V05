"""Best-effort lookup of a signal's unit/range from the retained _descriptive
MQTT message for its asset, via EMQX's retainer REST API. `_descriptive.signals`
is not a guaranteed project-wide schema (see design spec, Section 5) — any
shape mismatch or missing entry returns None rather than raising."""
from __future__ import annotations

import json
import urllib.parse

import httpx

from app.config import settings


def _api_base() -> str:
    return f"http://{settings.emqx_host}:{settings.emqx_api_port}/api/v5"


def _auth() -> tuple[str, str] | None:
    if settings.emqx_api_username:
        return (settings.emqx_api_username, settings.emqx_api_password or "")
    return None


async def get_descriptive_signal_meta(topic_prefix: str, signal_key: str) -> dict | None:
    topic = f"{topic_prefix}/_descriptive"
    try:
        encoded = urllib.parse.quote(topic, safe="")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{_api_base()}/retainer/message/{encoded}", auth=_auth())
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload_str = response.json().get("payload", "")
            if not payload_str:
                return None
            descriptive = json.loads(payload_str)
            entry = descriptive.get("signals", {}).get(signal_key)
            if not entry:
                return None
            rng = entry.get("range") or [None, None]
            return {"unit": entry.get("unit"), "min": rng[0], "max": rng[1]}
    except Exception:
        return None
