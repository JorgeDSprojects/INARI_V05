from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.dashboard import ChartCreate, ChartRead, ChartUpdate
from app.services import chart_service

router = APIRouter(tags=["charts"])


@router.post("/dashboards/{dashboard_id}/charts/", response_model=ChartRead, status_code=201)
async def create_chart(dashboard_id: str, body: ChartCreate, db: AsyncSession = Depends(get_db)):
    return await chart_service.create_chart(db, dashboard_id, body.model_dump())


@router.patch("/charts/{chart_id}", response_model=ChartRead)
async def update_chart(chart_id: str, body: ChartUpdate, db: AsyncSession = Depends(get_db)):
    return await chart_service.update_chart(db, chart_id, body.model_dump(exclude_unset=True))


@router.delete("/charts/{chart_id}", status_code=204)
async def delete_chart(chart_id: str, db: AsyncSession = Depends(get_db)):
    await chart_service.delete_chart(db, chart_id)
