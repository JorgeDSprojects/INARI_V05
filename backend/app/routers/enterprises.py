from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Enterprise
from app.schemas.uns import EnterpriseCreate, EnterpriseRead, EnterpriseUpdate
from app.services.uns_service import build_enterprise_topic
from app.services.mqtt_service import publish_descriptive, clear_retained

router = APIRouter(prefix="/enterprises", tags=["Enterprises"])


@router.get("/", response_model=list[EnterpriseRead])
async def list_enterprises(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Enterprise).order_by(Enterprise.name))
    return result.scalars().all()


@router.post("/", response_model=EnterpriseRead, status_code=status.HTTP_201_CREATED)
async def create_enterprise(body: EnterpriseCreate, db: AsyncSession = Depends(get_db)):
    obj = Enterprise(
        name=body.name,
        description=body.description,
        metadata_=body.metadata_,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{enterprise_id}", response_model=EnterpriseRead)
async def get_enterprise(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    return obj


@router.patch("/{enterprise_id}", response_model=EnterpriseRead)
async def update_enterprise(enterprise_id: str, body: EnterpriseUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")

    # Capture old state before any changes
    name_changing = body.name is not None and body.name != obj.name
    if name_changing:
        old_desc = build_enterprise_topic(obj, "_descriptive")
        old_info = build_enterprise_topic(obj, "_informative")
    old_desc_payload = obj.descriptive_payload
    old_info_payload = obj.informative_payload

    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)

    # Clear retained after rename (old topics)
    if name_changing:
        try: clear_retained(old_desc)
        except Exception: pass
        try: clear_retained(old_info)
        except Exception: pass

    # Sync payloads: publish if data, clear retained if payload was removed
    desc_topic = build_enterprise_topic(obj, "_descriptive")
    info_topic = build_enterprise_topic(obj, "_informative")

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


@router.post("/{enterprise_id}/publish", response_model=EnterpriseRead)
async def publish_enterprise(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    if obj.descriptive_payload:
        try:
            publish_descriptive(build_enterprise_topic(obj, "_descriptive"), obj.descriptive_payload)
        except Exception:
            pass
    if obj.informative_payload:
        try:
            publish_descriptive(build_enterprise_topic(obj, "_informative"), obj.informative_payload)
        except Exception:
            pass
    obj.last_published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{enterprise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enterprise(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Enterprise, enterprise_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    try:
        clear_retained(build_enterprise_topic(obj, "_descriptive"))
    except Exception:
        pass
    try:
        clear_retained(build_enterprise_topic(obj, "_informative"))
    except Exception:
        pass
    await db.delete(obj)
    await db.commit()
