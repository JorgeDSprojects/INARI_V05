# UNS_DASHBOARD/backend/app/services/chart_service.py
"""Chart write operations, shared by the REST router and the chat
agent's write tools. Extracted from app/routers/charts.py.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 4.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.dashboard import Chart, ChartSignal, Dashboard


async def create_chart(db: AsyncSession, dashboard_id: str, data: dict) -> Chart:
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    data = dict(data)
    signals_data = data.pop("signals", [])
    chart = Chart(dashboard_id=dashboard_id, **data)
    chart.signals = [ChartSignal(**s) for s in signals_data]
    db.add(chart)
    await db.commit()
    return await _get_chart_with_signals(db, chart.id)


async def update_chart(db: AsyncSession, chart_id: str, updates: dict) -> Chart:
    result = await db.execute(select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals)))
    chart = result.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    updates = dict(updates)
    signals_data = updates.pop("signals", None)
    for field, value in updates.items():
        setattr(chart, field, value)

    if signals_data is not None:
        chart.signals.clear()
        await db.flush()
        chart.signals = [ChartSignal(chart_id=chart_id, **s) for s in signals_data]

    await db.commit()
    return await _get_chart_with_signals(db, chart_id)


async def delete_chart(db: AsyncSession, chart_id: str) -> None:
    chart = await db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    await db.delete(chart)
    await db.commit()


async def _get_chart_with_signals(db: AsyncSession, chart_id: str) -> Chart:
    result = await db.execute(select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals)))
    return result.scalar_one()
