from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Line, Area
from app.schemas.uns import LineCreate, LineRead, LineUpdate
from app.services.uns_service import build_line_topic
from app.services.mqtt_service import publish_descriptive, clear_retained

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

    name_changing = body.name is not None and body.name != obj.name
    if name_changing:
        old_desc = await build_line_topic(obj, db, "_descriptive")
        old_info = await build_line_topic(obj, db, "_informative")
    old_desc_payload = obj.descriptive_payload
    old_info_payload = obj.informative_payload

    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)

    if name_changing:
        try: clear_retained(old_desc)
        except Exception: pass
        try: clear_retained(old_info)
        except Exception: pass

    desc_topic = await build_line_topic(obj, db, "_descriptive")
    info_topic = await build_line_topic(obj, db, "_informative")

    if old_desc_payload and not obj.descriptive_payload:
        try: clear_retained(desc_topic)
        except Exception: pass
    elif obj.descriptive_payload:
        try: publish_descriptive(desc_topic, obj.descriptive_payload)
        except Exception: pass

    if old_info_payload and not obj.informative_payload:
        try: clear_retained(info_topic)
        except Exception: pass
    elif obj.informative_payload:
        try: publish_descriptive(info_topic, obj.informative_payload)
        except Exception: pass

    if obj.descriptive_payload or obj.informative_payload:
        obj.last_published_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(obj)

    return obj


@router.post("/{line_id}/publish", response_model=LineRead)
async def publish_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(await build_line_topic(obj, db, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(await build_line_topic(obj, db, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line(area_id: str, line_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Line, line_id)
    if not obj or obj.area_id != area_id:
        raise HTTPException(status_code=404, detail="Line not found")
    try:
        clear_retained(await build_line_topic(obj, db, "_descriptive"))
    except Exception:
        pass
    try:
        clear_retained(await build_line_topic(obj, db, "_informative"))
    except Exception:
        pass
    await db.delete(obj)
    await db.commit()
