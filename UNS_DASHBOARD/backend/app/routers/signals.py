from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_historian_db
from app.services.descriptive_lookup import get_descriptive_signal_meta

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/catalog")
async def signal_catalog(
    topic_prefix: str = Query(..., min_length=1),
    historian_db: AsyncSession = Depends(get_historian_db),
):
    escaped_prefix = topic_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    topics_result = await historian_db.execute(
        text(
            "SELECT DISTINCT topic FROM mqtt_messages "
            "WHERE topic LIKE :prefix ESCAPE '\\' AND topic LIKE '%\\_informative' ESCAPE '\\' "
            "ORDER BY topic"
        ),
        {"prefix": f"{escaped_prefix}%"},
    )
    topics = [row[0] for row in topics_result.fetchall()]

    catalog = []
    for topic in topics:
        latest = await historian_db.execute(
            text("SELECT payload FROM mqtt_messages WHERE topic = :topic ORDER BY time DESC LIMIT 1"),
            {"topic": topic},
        )
        row = latest.first()
        payload = row[0] if row else None
        keys = [k for k in (payload or {}).keys() if k != "timestamp"]
        catalog.append({"topic": topic, "keys": keys})
    return catalog


@router.get("/descriptive")
async def signal_descriptive(
    topic_prefix: str = Query(..., min_length=1),
    signal_key: str = Query(..., min_length=1),
):
    meta = await get_descriptive_signal_meta(topic_prefix, signal_key)
    return meta or {}
