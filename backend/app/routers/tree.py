from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.uns import Enterprise, Site, Area, Line, Cell
from app.schemas.uns import EnterpriseTree
from app.services import subtree_service

router = APIRouter(prefix="/tree", tags=["Tree"])


class SubtreeOperationBody(BaseModel):
    source_id: str
    source_level: Literal["site", "area", "line", "cell", "asset"]
    target_parent_id: str


class PublishSubtreeBody(BaseModel):
    root_id: str
    root_level: Literal["enterprise", "site", "area", "line", "cell", "asset"]


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


@router.post("/copy")
async def copy_subtree(body: SubtreeOperationBody, db: AsyncSession = Depends(get_db)):
    try:
        result = await subtree_service.copy_subtree(
            body.source_id, body.source_level, body.target_parent_id, db
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/move")
async def move_subtree(body: SubtreeOperationBody, db: AsyncSession = Depends(get_db)):
    try:
        result = await subtree_service.move_subtree(
            body.source_id, body.source_level, body.target_parent_id, db
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/publish-subtree")
async def publish_subtree(body: PublishSubtreeBody, db: AsyncSession = Depends(get_db)):
    result = await subtree_service.publish_subtree(body.root_id, body.root_level, db)
    return result
