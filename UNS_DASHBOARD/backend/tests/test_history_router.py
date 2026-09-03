import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

DATABASE_URL = os.environ.get("DATABASE_URL")
HISTORIAN_DATABASE_URL = os.environ.get("HISTORIAN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and HISTORIAN_DATABASE_URL),
    reason="DATABASE_URL and HISTORIAN_DATABASE_URL required; requires both live Postgres instances",
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_history_endpoint_returns_points_for_relative_chart(client: TestClient):
    dashboard = client.post("/dashboards/", json={"name": "pytest History"}).json()
    chart = client.post(
        f"/dashboards/{dashboard['id']}/charts/",
        json={
            "name": "Temp",
            "chart_type": "timeseries",
            "data_mode": "historical",
            "historical_range_type": "relative",
            "historical_relative_rule": "24h",
            "layout_x": 0, "layout_y": 0, "layout_w": 12, "layout_h": 4,
            "signals": [{"topic": "pytest/site/_informative", "signal_key": "Amb_Temp_Avg"}],
        },
    ).json()

    response = client.get(f"/charts/{chart['id']}/history")
    assert response.status_code == 200
    assert "points" in response.json()

    client.delete(f"/dashboards/{dashboard['id']}")
