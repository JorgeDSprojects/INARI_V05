import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d postgres)"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _cleanup(client: TestClient):
    for d in client.get("/dashboards/").json():
        if d["name"].startswith("pytest"):
            client.delete(f"/dashboards/{d['id']}")


def test_create_list_publish_delete_dashboard(client: TestClient):
    _cleanup(client)
    created = client.post("/dashboards/", json={"name": "pytest Campo Sur", "description": "desc"}).json()
    assert created["status"] == "draft"

    listed = client.get("/dashboards/").json()
    assert any(d["id"] == created["id"] for d in listed)

    published = client.post(f"/dashboards/{created['id']}/publish").json()
    assert published["status"] == "published"
    assert published["published_at"] is not None

    detail = client.get(f"/dashboards/{created['id']}").json()
    assert detail["charts"] == []

    client.delete(f"/dashboards/{created['id']}")
    assert client.get(f"/dashboards/{created['id']}").status_code == 404
    _cleanup(client)
