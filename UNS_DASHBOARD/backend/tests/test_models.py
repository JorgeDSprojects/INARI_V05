import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import Base
from app.models.dashboard import Dashboard, Chart, ChartSignal

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as s:
        yield s
        await s.execute(Chart.__table__.delete())
        await s.execute(Dashboard.__table__.delete())
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_chart_and_signal_cascade_from_dashboard(session: AsyncSession):
    dashboard = Dashboard(name="pytest Campo Sur", description="test")
    session.add(dashboard)
    await session.flush()

    chart = Chart(
        dashboard_id=dashboard.id,
        name="Temp General",
        chart_type="timeseries",
        data_mode="historical",
        historical_range_type="relative",
        historical_relative_rule="30d",
        layout_x=0, layout_y=0, layout_w=12, layout_h=4,
        color="#3B82F6",
    )
    session.add(chart)
    await session.flush()

    signal = ChartSignal(
        chart_id=chart.id, topic="Enterprise/Site/_informative", signal_key="Amb_Temp_Avg",
        label="Amb Temp", unit="°C", source="manual",
    )
    session.add(signal)
    await session.commit()

    await session.delete(dashboard)
    await session.commit()

    remaining_charts = (
        await session.execute(Chart.__table__.select().where(Chart.dashboard_id == dashboard.id))
    ).fetchall()
    assert remaining_charts == []
