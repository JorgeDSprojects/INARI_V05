from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Line, Area
from app.schemas.uns import LineCreate, LineRead, LineUpdate

router = APIRouter(prefix="/areas/{area_id}/lines", tags=["Lines"])


@router.get("/", response_model=list[LineRead])
async def list_lines(area_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Line).where(Line.area_id == area_id).order_by(Line.name))
    return result.scalars().all()


@router.post("/", response_model=LineRead, status_code=status.HTTP_201_CREATED)
async def create_line(area_id: str, body: LineCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Area, area_id):
        raise HTTPException(status_code=404, detail="Area not found")
    obj = Line(area_id=area_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{line_id}", response_model=LineRead)
async def get_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    return obj


@router.patch("/{line_id}", response_model=LineRead)
async def update_line(area_id: str, line_id: str, body: LineUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    await db.delete(obj)
    await db.commit()
