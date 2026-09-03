from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.dashboard import Chart, Dashboard
from app.schemas.dashboard import DashboardCreate, DashboardDetailRead, DashboardRead, DashboardUpdate

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("/", response_model=list[DashboardRead])
async def list_dashboards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dashboard).order_by(Dashboard.name))
    return result.scalars().all()


@router.post("/", response_model=DashboardRead, status_code=201)
async def create_dashboard(body: DashboardCreate, db: AsyncSession = Depends(get_db)):
    dashboard = Dashboard(name=body.name, description=body.description)
    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard


@router.get("/{dashboard_id}", response_model=DashboardDetailRead)
async def get_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id)
        .options(selectinload(Dashboard.charts).selectinload(Chart.signals))
    )
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard


@router.patch("/{dashboard_id}", response_model=DashboardRead)
async def update_dashboard(dashboard_id: str, body: DashboardUpdate, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(dashboard, field, value)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    await db.delete(dashboard)
    await db.commit()


@router.post("/{dashboard_id}/publish", response_model=DashboardRead)
async def publish_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    dashboard.status = "published"
    dashboard.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard
