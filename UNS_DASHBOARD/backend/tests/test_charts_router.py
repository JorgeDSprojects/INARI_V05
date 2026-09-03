import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import AsyncSessionLocal

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _cleanup():
    import asyncio
    from sqlalchemy import delete
    from app.models.dashboard import Dashboard

    async def _run():
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Dashboard).where(Dashboard.name.like("pytest%")))
            await s.commit()

    asyncio.run(_run())


def test_create_update_replace_signals_and_delete_chart(client: TestClient):
    _cleanup()
    dashboard = client.post("/dashboards/", json={"name": "pytest Campo Sur"}).json()

    chart = client.post(
        f"/dashboards/{dashboard['id']}/charts/",
        json={
            "name": "Temp General",
            "chart_type": "timeseries",
            "data_mode": "live",
            "layout_x": 0, "layout_y": 0, "layout_w": 12, "layout_h": 4,
            "signals": [{"topic": "a/b/_informative", "signal_key": "Amb_Temp_Avg", "unit": "°C"}],
        },
    ).json()
    assert len(chart["signals"]) == 1

    updated = client.patch(
        f"/charts/{chart['id']}",
        json={"signals": [
            {"topic": "a/b/_informative", "signal_key": "Amb_Temp_Avg", "unit": "°C"},
            {"topic": "a/b/_informative", "signal_key": "Gen_Bear_Temp_Avg", "unit": "°C"},
        ]},
    ).json()
    assert len(updated["signals"]) == 2

    client.delete(f"/charts/{chart['id']}")
    detail = client.get(f"/dashboards/{dashboard['id']}").json()
    assert detail["charts"] == []
    _cleanup()
