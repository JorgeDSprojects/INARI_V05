from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.uns import Enterprise, Site, Area, Line, Cell
from app.schemas.uns import EnterpriseTree

router = APIRouter(prefix="/tree", tags=["Tree"])


@router.get("/", response_model=list[EnterpriseTree])
async def get_full_tree(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Enterprise)
        .options(
            selectinload(Enterprise.sites)
            .selectinload(Site.areas)
            .selectinload(Area.lines)
            .selectinload(Line.cells)
            .selectinload(Cell.assets)
        )
        .order_by(Enterprise.name)
    )
    return result.scalars().all()
