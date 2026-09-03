import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

HISTORIAN_DATABASE_URL = os.environ.get("HISTORIAN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not HISTORIAN_DATABASE_URL, reason="HISTORIAN_DATABASE_URL not set; requires a live UNS_HISTORIAN Postgres"
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_catalog_lists_topics_and_keys_under_prefix(client: TestClient):
    from sqlalchemy import create_engine, text

    engine = create_engine(HISTORIAN_DATABASE_URL.replace("+asyncpg", "+psycopg"))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_catalog/%'"))
        conn.execute(
            text(
                "INSERT INTO mqtt_messages (time, topic, payload, qos, retain) VALUES "
                "(now(), 'pytest_catalog/gen/_informative', '{\"Gen_RPM_Avg\": 1300}', 1, false)"
            )
        )

    response = client.get("/signals/catalog", params={"topic_prefix": "pytest_catalog"})
    assert response.status_code == 200
    topics = response.json()
    assert any(t["topic"] == "pytest_catalog/gen/_informative" and "Gen_RPM_Avg" in t["keys"] for t in topics)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_catalog/%'"))
