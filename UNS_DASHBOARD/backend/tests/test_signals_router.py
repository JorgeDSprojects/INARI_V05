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


def _find_leaf(nodes: list[dict], topic: str) -> dict | None:
    for node in nodes:
        if node.get("leaf", {}).get("topic") == topic:
            return node["leaf"]
        found = _find_leaf(node["children"], topic)
        if found:
            return found
    return None


def test_tree_historical_nests_topics_and_lists_keys_for_both_suffixes(client: TestClient):
    from sqlalchemy import create_engine, text

    engine = create_engine(HISTORIAN_DATABASE_URL.replace("+asyncpg", "+psycopg"))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_tree/%'"))
        conn.execute(
            text(
                "INSERT INTO mqtt_messages (time, topic, payload, qos, retain) VALUES "
                "(now(), 'pytest_tree/gen/_informative', '{\"Gen_RPM_Avg\": 1300}', 1, false), "
                "(now(), 'pytest_tree/gen/_analytical', '{\"Health_Score\": 0.92}', 1, false)"
            )
        )

    response = client.get("/signals/tree/historical", params={"topic_prefix": "pytest_tree"})
    assert response.status_code == 200
    tree = response.json()

    informative_leaf = _find_leaf(tree, "pytest_tree/gen/_informative")
    assert informative_leaf["topic_type"] == "informative"
    assert "Gen_RPM_Avg" in informative_leaf["keys"]

    analytical_leaf = _find_leaf(tree, "pytest_tree/gen/_analytical")
    assert analytical_leaf["topic_type"] == "analytical"
    assert "Health_Score" in analytical_leaf["keys"]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mqtt_messages WHERE topic LIKE 'pytest_tree/%'"))
