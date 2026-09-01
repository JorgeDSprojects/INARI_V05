from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.uns import Site, Enterprise
from app.schemas.uns import SiteCreate, SiteRead, SiteUpdate

router = APIRouter(prefix="/enterprises/{enterprise_id}/sites", tags=["Sites"])


@router.get("/", response_model=list[SiteRead])
async def list_sites(enterprise_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).where(Site.enterprise_id == enterprise_id).order_by(Site.name))
    return result.scalars().all()


@router.post("/", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
async def create_site(enterprise_id: str, body: SiteCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Enterprise, enterprise_id):
        raise HTTPException(status_code=404, detail="Enterprise not found")
    obj = Site(enterprise_id=enterprise_id, name=body.name, description=body.description, metadata_=body.metadata_)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{site_id}", response_model=SiteRead)
async def get_site(enterprise_id: str, site_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    return obj


@router.patch("/{site_id}", response_model=SiteRead)
async def update_site(enterprise_id: str, site_id: str, body: SiteUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    for field, value in body.model_dump(exclude_unset=True, by_alias=False).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(enterprise_id: str, site_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Site, site_id)
    if not obj or obj.enterprise_id != enterprise_id:
        raise HTTPException(status_code=404, detail="Site not found")
    await db.delete(obj)
    await db.commit()
