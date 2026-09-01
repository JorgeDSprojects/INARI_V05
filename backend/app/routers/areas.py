from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Area, Site
from app.schemas.uns import AreaCreate, AreaRead, AreaUpdate
from app.services.uns_service import build_area_topic
from app.services.mqtt_service import publish_descriptive, clear_retained

router = APIRouter(prefix="/sites/{site_id}/areas", tags=["Areas"])


@router.get("/", response_model=list[AreaRead])
async def list_areas(site_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Area).where(Area.site_id == site_id).order_by(Area.name))
    return result.scalars().all()


@router.post("/", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
async def create_area(site_id: str, body: AreaCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Site, site_id):
        raise HTTPException(status_code=404, detail="Site not found")
    obj = Area(site_id=site_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{area_id}", response_model=AreaRead)
async def get_area(site_id: str, area_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    return obj


@router.patch("/{area_id}", response_model=AreaRead)
async def update_area(site_id: str, area_id: str, body: AreaUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")

    name_changing = body.name is not None and body.name != obj.name
    if name_changing:
        old_desc = await build_area_topic(obj, db, "_descriptive")
        old_info = await build_area_topic(obj, db, "_informative")

    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)

    if name_changing:
        try:
            clear_retained(old_desc)
        except Exception:
            pass
        try:
            clear_retained(old_info)
        except Exception:
            pass

    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_area_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_area_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    if obj.descriptive_payload or obj.informative_payload:
        obj.last_published_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(obj)

    return obj


@router.post("/{area_id}/publish", response_model=AreaRead)
async def publish_area(site_id: str, area_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_area_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_area_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_area(site_id: str, area_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Area, area_id)
    if not obj or obj.site_id != site_id:
        raise HTTPException(status_code=404, detail="Area not found")
    try:
        clear_retained(await build_area_topic(obj, db, "_descriptive"))
    except Exception:
        pass
    try:
        clear_retained(await build_area_topic(obj, db, "_informative"))
    except Exception:
        pass
    await db.delete(obj)
    await db.commit()
