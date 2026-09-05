"""Applies TimescaleDB compression + retention policies to Silver's own
hypertables, idempotently, from configured settings. Applies only to
UNS_SILVER's own tables — never touches UNS_HISTORIAN's bronze retention.

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 4.
"""
from __future__ import annotations

import psycopg
from psycopg import sql

from app.config import Settings

_COMPRESSED_HYPERTABLES = ("silver_readings", "silver_events")
# Without a segmentby, a compressed chunk cannot be pruned by the topic/signal
# predicates every agent query uses -- the whole chunk has to be decompressed.
_COMPRESSION_SEGMENTBY = {
    "silver_readings": "topic, signal_key",
    "silver_events": "topic, event_key",
}
_AGGREGATE_RETENTION_SETTINGS = {
    "silver_readings_1m": "agg_1m_retention_days",
    "silver_readings_1h": "agg_1h_retention_days",
}
_CONTINUOUS_AGGREGATE_REFRESH_SCHEDULES = {
    "silver_readings_1m": {
        "start_offset": "1 hour",
        "end_offset": "1 minute",
        "schedule_interval": "1 minute",
    },
    "silver_readings_1h": {
        "start_offset": "1 day",
        "end_offset": "1 hour",
        "schedule_interval": "1 hour",
    },
}


def apply_policies(conn: psycopg.Connection, settings: Settings) -> None:
    with conn.cursor() as cur:
        for table in _COMPRESSED_HYPERTABLES:
            cur.execute(
                sql.SQL(
                    "ALTER TABLE {} SET (timescaledb.compress, "
                    "timescaledb.compress_segmentby = {}, timescaledb.compress_orderby = 'time DESC')"
                ).format(sql.Identifier(table), sql.Literal(_COMPRESSION_SEGMENTBY[table]))
            )
            cur.execute("SELECT remove_compression_policy(%s::regclass, if_exists => TRUE)", (table,))
            cur.execute(
                "SELECT add_compression_policy(%s::regclass, %s::interval)",
                (table, f"{settings.raw_compress_after_days} days"),
            )
            cur.execute("SELECT remove_retention_policy(%s::regclass, if_exists => TRUE)", (table,))
            cur.execute(
                "SELECT add_retention_policy(%s::regclass, %s::interval)",
                (table, f"{settings.raw_retention_days} days"),
            )

        for table, setting_name in _AGGREGATE_RETENTION_SETTINGS.items():
            days = getattr(settings, setting_name)
            cur.execute("SELECT remove_retention_policy(%s::regclass, if_exists => TRUE)", (table,))
            if days > 0:
                cur.execute(
                    "SELECT add_retention_policy(%s::regclass, %s::interval)", (table, f"{days} days")
                )

        for table, sched in _CONTINUOUS_AGGREGATE_REFRESH_SCHEDULES.items():
            cur.execute(
                "SELECT remove_continuous_aggregate_policy(%s::regclass, if_exists => TRUE)", (table,)
            )
            cur.execute(
                "SELECT add_continuous_aggregate_policy(%s::regclass, "
                "start_offset => %s::interval, end_offset => %s::interval, "
                "schedule_interval => %s::interval)",
                (table, sched["start_offset"], sched["end_offset"], sched["schedule_interval"]),
            )
    conn.commit()


def backfill_continuous_aggregates_if_empty(settings: Settings) -> None:
    """One-time full backfill for a continuous aggregate that has no
    materialized data yet. A refresh policy only ever materializes its own
    rolling window going forward, never pre-existing history -- without
    this, data older than the policy's start_offset stays permanently
    invisible to the aggregate. Guarded by an emptiness check so this
    doesn't re-run an expensive full backfill on every process restart.
    Runs on its own autocommit connection because refresh_continuous_aggregate
    cannot execute inside a transaction block."""
    backfill_conn = psycopg.connect(settings.database_url, autocommit=True)
    try:
        with backfill_conn.cursor() as cur:
            for table in _CONTINUOUS_AGGREGATE_REFRESH_SCHEDULES:
                cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
                (row_count,) = cur.fetchone()
                if row_count == 0:
                    cur.execute("CALL refresh_continuous_aggregate(%s::regclass, NULL, NULL)", (table,))
    finally:
        backfill_conn.close()
