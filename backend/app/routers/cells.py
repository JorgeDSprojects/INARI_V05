from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Cell, Line
from app.schemas.uns import CellCreate, CellRead, CellUpdate
from app.services.uns_service import build_cell_topic
from app.services.mqtt_service import publish_descriptive

router = APIRouter(prefix="/lines/{line_id}/cells", tags=["Cells"])


@router.get("/", response_model=list[CellRead])
async def list_cells(line_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Cell).where(Cell.line_id == line_id).order_by(Cell.name))
    return result.scalars().all()


@router.post("/", response_model=CellRead, status_code=status.HTTP_201_CREATED)
async def create_cell(line_id: str, body: CellCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Line, line_id):
        raise HTTPException(status_code=404, detail="Line not found")
    obj = Cell(line_id=line_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{cell_id}", response_model=CellRead)
async def get_cell(line_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    return obj


@router.patch("/{cell_id}", response_model=CellRead)
async def update_cell(line_id: str, cell_id: str, body: CellUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{cell_id}/publish", response_model=CellRead)
async def publish_cell(line_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_cell_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_cell_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{cell_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cell(line_id: str, cell_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Cell, cell_id)
    if not obj or obj.line_id != line_id:
        raise HTTPException(status_code=404, detail="Cell not found")
    await db.delete(obj)
    await db.commit()
