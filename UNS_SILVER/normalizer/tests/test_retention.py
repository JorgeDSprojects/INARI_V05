import os

import psycopg
import pytest

from app.config import load_settings
from app.retention import apply_policies

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres with UNS_SILVER's schema applied"
)


@pytest.fixture
def conn():
    connection = psycopg.connect(DATABASE_URL, autocommit=False)
    yield connection
    connection.close()


def test_apply_policies_does_not_raise(conn):
    settings = load_settings({
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "365",
    })
    apply_policies(conn, settings)


def test_apply_policies_is_idempotent(conn):
    settings = load_settings({
        "RAW_COMPRESS_AFTER_DAYS": "7", "RAW_RETENTION_DAYS": "90",
        "AGG_1M_RETENTION_DAYS": "0", "AGG_1H_RETENTION_DAYS": "0",
    })
    apply_policies(conn, settings)
    apply_policies(conn, settings)  # must not raise on re-application


def test_apply_policies_configures_continuous_aggregate_refresh(conn):
    """Verify that continuous aggregate refresh policies are applied idempotently."""
    settings = load_settings({
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
