from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_historian_db
from app.services.descriptive_lookup import get_descriptive_signal_meta
from app.services.live_topics import discover_live_topics
from app.services.signal_tree import build_tree, topic_type_of

router = APIRouter(prefix="/signals", tags=["signals"])

_SUFFIX_CLAUSE = "(topic LIKE '%\\_informative' ESCAPE '\\' OR topic LIKE '%\\_analytical' ESCAPE '\\')"


@router.get("/tree/historical")
async def signal_tree_historical(
    topic_prefix: str = Query(""),
    historian_db: AsyncSession = Depends(get_historian_db),
):
    if topic_prefix:
        escaped_prefix = topic_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where_sql = f"topic LIKE :prefix ESCAPE '\\' AND {_SUFFIX_CLAUSE}"
        params = {"prefix": f"{escaped_prefix}%"}
    else:
        where_sql = _SUFFIX_CLAUSE
        params = {}

    topics_result = await historian_db.execute(
        text(f"SELECT DISTINCT topic FROM mqtt_messages WHERE {where_sql} ORDER BY topic"),
        params,
    )
    topics = [row[0] for row in topics_result.fetchall()]

    entries = []
    for topic in topics:
        latest = await historian_db.execute(
            text("SELECT payload FROM mqtt_messages WHERE topic = :topic ORDER BY time DESC LIMIT 1"),
            {"topic": topic},
        )
        row = latest.first()
        payload = row[0] if row else None
        keys = [k for k in payload.keys() if k != "timestamp"] if isinstance(payload, dict) else []
        topic_type = topic_type_of(topic)
        if topic_type:
            entries.append((topic, topic_type, keys))
    return build_tree(entries)


@router.get("/tree/live")
async def signal_tree_live():
    redis_client = aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    try:
        entries = await discover_live_topics(redis_client)
        return build_tree(entries)
    finally:
        await redis_client.aclose()


@router.get("/descriptive")
async def signal_descriptive(
    topic_prefix: str = Query(..., min_length=1),
    signal_key: str = Query(..., min_length=1),
):
    meta = await get_descriptive_signal_meta(topic_prefix, signal_key)
    return meta or {}
