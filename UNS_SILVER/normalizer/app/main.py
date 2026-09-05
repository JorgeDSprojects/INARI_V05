"""Entrypoint: connects to uns_silver_postgres and uns_historian_postgres
(read-only in practice), applies retention/compression policies, LISTENs
for `silver_updates` notifications from the historian ingestor, and
processes newly-arrived bronze rows. Falls back to polling every
NORMALIZER_POLL_INTERVAL_SECONDS in case a notification is missed (e.g.
across a restart).

See docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 3.
"""
from __future__ import annotations

import logging
import signal
import threading

import psycopg

from app import retention
from app.batch import process_batch
from app.config import Settings, load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("uns_silver.normalizer")


def _process_until_caught_up(
    historian_conn: psycopg.Connection, silver_conn: psycopg.Connection, settings: Settings
) -> None:
    while True:
        processed = process_batch(historian_conn, silver_conn, settings)
        if processed:
            logger.info("Processed %d bronze row(s)", processed)
        if processed < settings.batch_size:
            break


def _safe_process_until_caught_up(
    historian_conn: psycopg.Connection, silver_conn: psycopg.Connection, settings: Settings
) -> None:
    """Single guarded entry point shared by the startup catch-up and the main
    loop. The startup call matters most: the watermark starts at 0, so the very
    first run replays the entire bronze history in one uninterrupted sequence of
    batches -- the largest, least-controlled work the process ever does."""
    try:
        _process_until_caught_up(historian_conn, silver_conn, settings)
    except Exception:
        logger.exception("Error while processing batch, rolling back and retrying next cycle")
        try:
            silver_conn.rollback()
        except Exception:
            logger.exception("Rollback also failed; connection may need to be recreated")


def main() -> None:
    settings = load_settings()

    silver_conn = psycopg.connect(settings.database_url, autocommit=False)
    retention.apply_policies(silver_conn, settings)

    historian_conn = psycopg.connect(settings.historian_database_url, autocommit=True)
    historian_conn.execute("LISTEN silver_updates")

    stop_event = threading.Event()

    def _handle_sigterm(signum, frame):
        logger.info("Received SIGTERM, shutting down")
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("Silver normalizer started, listening for silver_updates")
    _safe_process_until_caught_up(historian_conn, silver_conn, settings)

    # Must run after the startup catch-up above, not before: on a fresh deploy
    # against a historian that already holds bronze history, silver_readings
    # is still empty until catch-up ingests it. Backfilling any earlier (e.g.
    # from inside apply_policies, before catch-up) would find the aggregates
    # empty, run once, materialize nothing, and never get another chance --
    # the pre-existing backlog would stay permanently invisible to the
    # aggregates. Running it here guarantees silver_readings already holds
    # the ingested history the first time this executes.
    retention.backfill_continuous_aggregates_if_empty(settings)

    while not stop_event.is_set():
        # Blocks up to poll_interval_seconds; wakes early on a NOTIFY, or
        # simply times out (empty iteration) as the polling fallback.
        # A dropped historian_conn here intentionally propagates and exits the
        # process: Docker's `restart: unless-stopped` brings it back, which
        # re-establishes the LISTEN registration a reconnect-in-place would
        # silently lose. This is a deliberate choice, not an unhandled gap.
        for _ in historian_conn.notifies(timeout=settings.poll_interval_seconds):
            break
        if stop_event.is_set():
            break
        _safe_process_until_caught_up(historian_conn, silver_conn, settings)

    silver_conn.close()
    historian_conn.close()


if __name__ == "__main__":
    main()
