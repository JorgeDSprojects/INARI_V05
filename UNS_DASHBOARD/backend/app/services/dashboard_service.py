# UNS_DASHBOARD/backend/app/services/dashboard_service.py
"""Dashboard write operations, shared by the REST router and the chat
agent's write tools. Extracted from app/routers/dashboards.py so both
callers run the exact same logic.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 4.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard


async def create_dashboard(db: AsyncSession, name: str, description: str | None = None) -> Dashboard:
    dashboard = Dashboard(name=name, description=description)
    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard


async def publish_dashboard(db: AsyncSession, dashboard_id: str) -> Dashboard:
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    dashboard.status = "published"
    dashboard.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard
