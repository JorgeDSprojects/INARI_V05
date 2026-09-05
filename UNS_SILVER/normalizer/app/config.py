"""Environment-variable configuration for the Silver normalizer."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    historian_database_url: str
    poll_interval_seconds: float
    batch_size: int
    max_flatten_depth: int
    max_flatten_keys: int
    raw_compress_after_days: int
    raw_retention_days: int
    agg_1m_retention_days: int
    agg_1h_retention_days: int


def load_settings(env: dict[str, str] | None = None) -> Settings:
    e = env if env is not None else os.environ
    return Settings(
        database_url=e.get(
            "DATABASE_URL", "postgresql://silver:silverpassword@uns_silver_postgres:5432/uns_silver"
        ),
        historian_database_url=e.get(
            "HISTORIAN_DATABASE_URL",
            "postgresql://historian:historianpassword@uns_historian_postgres:5432/uns_historian",
        ),
        poll_interval_seconds=float(e.get("NORMALIZER_POLL_INTERVAL_SECONDS", "10")),
        batch_size=int(e.get("NORMALIZER_BATCH_SIZE", "2000")),
        max_flatten_depth=int(e.get("MAX_FLATTEN_DEPTH", "6")),
        max_flatten_keys=int(e.get("MAX_FLATTEN_KEYS_PER_MESSAGE", "500")),
        raw_compress_after_days=int(e.get("RAW_COMPRESS_AFTER_DAYS", "7")),
        raw_retention_days=int(e.get("RAW_RETENTION_DAYS", "90")),
        agg_1m_retention_days=int(e.get("AGG_1M_RETENTION_DAYS", "0")),
        agg_1h_retention_days=int(e.get("AGG_1H_RETENTION_DAYS", "0")),
    )
