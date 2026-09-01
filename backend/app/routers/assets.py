from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Asset, Cell
from app.schemas.uns import AssetCreate, AssetRead, AssetUpdate
from app.services.uns_service import build_uns_topic
from app.services.mqtt_service import publish_descriptive

router = APIRouter(prefix="/cells/{cell_id}/assets", tags=["Assets"])


@router.get("/", response_model=list[AssetRead])
async def list_assets(cell_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.cell_id == cell_id).order_by(Asset.name))
    return result.scalars().all()


@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(cell_id: str, body: AssetCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Cell, cell_id):
        raise HTTPException(status_code=404, detail="Cell not found")
    obj = Asset(
        cell_id=cell_id,
        name=body.name,
        description=body.description,
        descriptive_payload=body.descriptive_payload or {},
    )
    db.add(obj)
    await db.flush()

    topic = await build_uns_topic(obj, db)
    obj.uns_topic = topic

    await db.commit()
    await db.refresh(obj)

    if obj.descriptive_payload:
        try:
            publish_descriptive(topic, obj.descriptive_payload)
        except Exception:
            pass

    return obj


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return obj


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(cell_id: str, asset_id: str, body: AssetUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)

    if body.name is not None:
        obj.uns_topic = await build_uns_topic(obj, db)

    await db.commit()
    await db.refresh(obj)

    if obj.descriptive_payload and obj.uns_topic:
        try:
            publish_descriptive(obj.uns_topic, obj.descriptive_payload)
        except Exception:
            pass

    return obj


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    await db.delete(obj)
    await db.commit()


@router.post("/{asset_id}/publish", response_model=AssetRead)
async def publish_asset(cell_id: str, asset_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Asset, asset_id)
    if not obj or obj.cell_id != cell_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not obj.uns_topic:
        obj.uns_topic = await build_uns_topic(obj, db)
        await db.commit()
        await db.refresh(obj)
    if obj.descriptive_payload:
        publish_descriptive(obj.uns_topic, obj.descriptive_payload)
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj
