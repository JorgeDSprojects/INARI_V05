import os

import psycopg
import pytest

from app.config import load_settings
from app.retention import apply_policies, backfill_continuous_aggregates_if_empty

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)

# NOTE: every settings dict below must carry DATABASE_URL -- backfill_continuous_
# aggregates_if_empty opens a second, autocommit connection of its own for the
# continuous-aggregate backfill (refresh_continuous_aggregate cannot run inside
# a transaction block), and that connection is built from settings, not from
# the `conn` fixture.


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    yield connection
    connection.close()


def test_apply_policies_does_not_raise(conn):
    settings = load_settings({
        "DATABASE_URL": DATABASE_URL,
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "365",
    })
    apply_policies(conn, settings)


def test_apply_policies_is_idempotent(conn):
    settings = load_settings({
        "DATABASE_URL": DATABASE_URL,
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "0",
    })
    apply_policies(conn, settings)
    apply_policies(conn, settings)  # must not raise on re-application


def test_apply_policies_configures_continuous_aggregate_refresh(conn):
    """Verify that continuous aggregate refresh policies are applied idempotently."""
    settings = load_settings({
        "DATABASE_URL": DATABASE_URL,
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "365",
    })
    # First call should succeed without raising
    apply_policies(conn, settings)

    # Verify that refresh jobs exist for the continuous aggregates
    with conn.cursor() as cur:
        cur.execute(
            "SELECT proc_name, hypertable_name FROM timescaledb_information.jobs "
            "WHERE proc_name = 'policy_refresh_continuous_aggregate' "
            "AND hypertable_name IN ('silver_readings_1m', 'silver_readings_1h') "
            "ORDER BY hypertable_name"
        )
        jobs = cur.fetchall()

    # Both aggregates should have refresh jobs
    assert len(jobs) == 2, f"Expected 2 refresh jobs, got {len(jobs)}: {jobs}"
    assert all(job[0] == "policy_refresh_continuous_aggregate" for job in jobs), "All jobs should be refresh policies"
    assert set(job[1] for job in jobs) == {"silver_readings_1m", "silver_readings_1h"}, "Both aggregates should have jobs"

    # Second call should also succeed (idempotence check)
    apply_policies(conn, settings)

    # Verify jobs still exist after second call
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM timescaledb_information.jobs "
            "WHERE proc_name = 'policy_refresh_continuous_aggregate' "
            "AND hypertable_name IN ('silver_readings_1m', 'silver_readings_1h')"
        )
        count = cur.fetchone()[0]
    assert count == 2, f"Expected 2 refresh jobs after idempotent call, got {count}"


def test_apply_policies_registers_compression_segmentby(conn):
    """Without a segmentby, a compressed chunk cannot be pruned by the
    topic/signal predicates every query uses and must be decompressed whole."""
    settings = load_settings({
        "DATABASE_URL": DATABASE_URL,
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "0",
    })
    apply_policies(conn, settings)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT hypertable_name, attname, segmentby_column_index, orderby_column_index, orderby_asc "
            "FROM timescaledb_information.compression_settings "
            "WHERE hypertable_name IN ('silver_readings', 'silver_events') "
            "ORDER BY hypertable_name, attname"
        )
        rows = cur.fetchall()
    conn.rollback()

    segmentby = {(r[0], r[1]) for r in rows if r[2] is not None}
    assert segmentby == {
        ("silver_events", "topic"), ("silver_events", "event_key"),
        ("silver_readings", "topic"), ("silver_readings", "signal_key"),
    }, f"unexpected segmentby columns: {rows}"

    orderby = {(r[0], r[1], r[4]) for r in rows if r[3] is not None}
    assert orderby == {("silver_events", "time", False), ("silver_readings", "time", False)}, (
        f"expected 'time DESC' orderby on both tables, got: {rows}"
    )


def test_backfill_continuous_aggregates_if_empty_backfills_when_readings_exist(conn):
    """A refresh policy only materializes its own rolling window going forward;
    pre-existing history needs an explicit one-time refresh. This backfill is
    intentionally not part of apply_policies -- it must run after startup
    catch-up has populated silver_readings, not before (see main.py)."""
    settings = load_settings({
        "DATABASE_URL": DATABASE_URL,
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "0",
    })
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM silver_readings")
        reading_count = cur.fetchone()[0]
    conn.rollback()
    if reading_count == 0:
        pytest.skip("no silver_readings rows to aggregate")

    backfill_continuous_aggregates_if_empty(settings)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM silver_readings_1h")
        assert cur.fetchone()[0] > 0, "1h aggregate is still empty after backfill_continuous_aggregates_if_empty"
    conn.rollback()


def test_backfill_continuous_aggregates_if_empty_skips_when_already_populated(conn):
    """Guards against re-running an expensive full backfill on every process
    restart: once an aggregate has any rows, the function must not touch it
    again (verified indirectly here by simply confirming it doesn't raise and
    doesn't reduce the row count)."""
    settings = load_settings({
        "DATABASE_URL": DATABASE_URL,
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "0",
    })
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM silver_readings_1h")
        agg_count_before = cur.fetchone()[0]
    conn.rollback()
    if agg_count_before == 0:
        pytest.skip("silver_readings_1h is empty; nothing to verify the skip-guard against")

    backfill_continuous_aggregates_if_empty(settings)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM silver_readings_1h")
        agg_count_after = cur.fetchone()[0]
    conn.rollback()
    assert agg_count_after == agg_count_before, "backfill should not touch an already-populated aggregate"
