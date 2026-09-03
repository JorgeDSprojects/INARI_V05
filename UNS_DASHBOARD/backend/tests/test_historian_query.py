from datetime import datetime, timedelta, timezone

from app.services.historian_query import choose_bucket_seconds, resolve_relative_range

NOW = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)


def test_choose_bucket_seconds_for_one_hour_range():
    assert choose_bucket_seconds(3600) == 5


def test_choose_bucket_seconds_for_one_month_range():
    assert choose_bucket_seconds(30 * 86400) == 3600


def test_resolve_relative_range_1h():
    start, end = resolve_relative_range("1h", NOW)
    assert end == NOW
    assert start == NOW - timedelta(hours=1)


def test_resolve_relative_range_30d():
    start, end = resolve_relative_range("30d", NOW)
    assert start == NOW - timedelta(days=30)


def test_resolve_relative_range_unknown_rule_raises():
    import pytest
    with pytest.raises(ValueError):
        resolve_relative_range("banana", NOW)


# --- Task 8 ---
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.services.historian_query import query_history

HISTORIAN_DATABASE_URL = os.environ.get("HISTORIAN_DATABASE_URL")

pytestmark_db = pytest.mark.skipif(
    not HISTORIAN_DATABASE_URL,
    reason="HISTORIAN_DATABASE_URL not set; requires a live UNS_HISTORIAN Postgres",
)


@pytest.fixture
async def historian_session():
    engine = create_async_engine(HISTORIAN_DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as s:
        await s.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'"))
        await s.commit()
        yield s
        await s.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest/%'"))
        await s.commit()
    await engine.dispose()


@pytestmark_db
@pytest.mark.asyncio
async def test_query_history_merges_two_topics_by_bucket(historian_session: AsyncSession):
    from datetime import datetime, timezone
    t0 = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 3, 10, 0, 2, tzinfo=timezone.utc)
    await historian_session.execute(
        text(
            "INSERT INTO mqtt_messages (time, topic, payload, qos, retain) VALUES "
            "(:t0, 'pytest/site/_informative', '{\"Amb_Temp_Avg\": 19}', 1, false), "
            "(:t1, 'pytest/gen/_informative', '{\"Gen_Bear_Temp_Avg\": 58}', 1, false)"
        ),
        {"t0": t0, "t1": t1},
    )
    await historian_session.commit()

    rows = await query_history(
        historian_session,
        signals=[("pytest/site/_informative", "Amb_Temp_Avg"), ("pytest/gen/_informative", "Gen_Bear_Temp_Avg")],
        start=t0,
        end=t1,
    )
    assert len(rows) >= 1
    merged = {k: v for row in rows for k, v in row.items() if k != "time"}
    assert merged.get("Amb_Temp_Avg") == 19
    assert merged.get("Gen_Bear_Temp_Avg") == 58
