from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app.database import get_db
from app.models.dashboard import Chart, ChartSignal, Dashboard
from app.schemas.dashboard import ChartCreate, ChartRead, ChartUpdate

router = APIRouter(tags=["charts"])


@router.post("/dashboards/{dashboard_id}/charts/", response_model=ChartRead, status_code=201)
async def create_chart(dashboard_id: str, body: ChartCreate, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    data = body.model_dump(exclude={"signals"})
    chart = Chart(dashboard_id=dashboard_id, **data)
    chart.signals = [ChartSignal(**s.model_dump()) for s in body.signals]
    db.add(chart)
    await db.commit()
    return await _get_chart_with_signals(db, chart.id)


@router.patch("/charts/{chart_id}", response_model=ChartRead)
async def update_chart(chart_id: str, body: ChartUpdate, db: AsyncSession = Depends(get_db)):
    chart = await db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    updates = body.model_dump(exclude_unset=True, exclude={"signals"})
    for field, value in updates.items():
        setattr(chart, field, value)

    if body.signals is not None:
        chart.signals.clear()
        await db.flush()
        chart.signals = [ChartSignal(chart_id=chart_id, **s.model_dump()) for s in body.signals]

    await db.commit()
    return await _get_chart_with_signals(db, chart_id)


@router.delete("/charts/{chart_id}", status_code=204)
async def delete_chart(chart_id: str, db: AsyncSession = Depends(get_db)):
    chart = await db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    await db.delete(chart)
    await db.commit()


async def _get_chart_with_signals(db: AsyncSession, chart_id: str) -> Chart:
    result = await db.execute(
        select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals))
    )
    return result.scalar_one()
