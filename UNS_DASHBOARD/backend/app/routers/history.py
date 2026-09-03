from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.database import get_db, get_historian_db
from app.models.dashboard import Chart
from app.services.historian_query import query_history, resolve_relative_range

router = APIRouter(tags=["history"])


@router.get("/charts/{chart_id}/history")
async def get_chart_history(
    chart_id: str,
    db: AsyncSession = Depends(get_db),
    historian_db: AsyncSession = Depends(get_historian_db),
):
    result = await db.execute(
        select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals))
    )
    chart = result.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    if chart.data_mode != "historical":
        raise HTTPException(status_code=400, detail="Chart is not in historical data_mode")

    if chart.historical_range_type == "relative":
        if not chart.historical_relative_rule:
            raise HTTPException(status_code=400, detail="Chart has no historical_relative_rule configured")
        start, end = resolve_relative_range(chart.historical_relative_rule, datetime.now(timezone.utc))
    elif chart.historical_range_type == "fixed":
        if not chart.historical_from or not chart.historical_to:
            raise HTTPException(status_code=400, detail="Chart has no historical_from/historical_to configured")
        start, end = chart.historical_from, chart.historical_to
    else:
        raise HTTPException(status_code=400, detail="Chart has no historical range configured")

    signals = [(s.topic, s.signal_key) for s in chart.signals]
    points = await query_history(historian_db, signals, start, end)
    return {"points": points}
