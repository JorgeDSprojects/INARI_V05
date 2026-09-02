# UNS_HISTORIAN/ingestor/app/config.py
"""Environment-variable configuration for the ingestor."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    emqx_host: str
    emqx_port: int
    mqtt_topic_filter: str
    mqtt_client_id: str
    flush_interval_seconds: float
    flush_max_rows: int
    buffer_max_rows: int


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        database_url=e.get(
            "DATABASE_URL", "postgresql://historian:historianpassword@postgres:5432/uns_historian"
        ),
        emqx_host=e.get("EMQX_HOST", "emqx"),
        emqx_port=int(e.get("EMQX_PORT", "1883")),
        mqtt_topic_filter=e.get("MQTT_TOPIC_FILTER", "#"),
        mqtt_client_id=e.get("MQTT_CLIENT_ID", "uns-historian-ingestor"),
        flush_interval_seconds=float(e.get("FLUSH_INTERVAL_SECONDS", "2")),
        flush_max_rows=int(e.get("FLUSH_MAX_ROWS", "500")),
        buffer_max_rows=int(e.get("BUFFER_MAX_ROWS", "20000")),
    )
