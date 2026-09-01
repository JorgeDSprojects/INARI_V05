from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.broker import Broker
from app.schemas.broker import (
    BrokerCreate,
    BrokerRead,
    BrokerStatus,
    BrokerTestResult,
    BrokerUpdate,
)
from app.services import broker_service

router = APIRouter(prefix="/brokers", tags=["Brokers"])


@router.get("/", response_model=list[BrokerRead])
async def list_brokers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Broker).order_by(Broker.label))
    return result.scalars().all()


@router.post("/", response_model=BrokerRead, status_code=status.HTTP_201_CREATED)
async def create_broker(body: BrokerCreate, db: AsyncSession = Depends(get_db)):
    obj = Broker(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{broker_id}", response_model=BrokerRead)
async def get_broker(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    return obj


@router.put("/{broker_id}", response_model=BrokerRead)
async def update_broker(
    broker_id: str, body: BrokerUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broker(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    await db.delete(obj)
    await db.commit()


@router.get("/{broker_id}/status", response_model=BrokerStatus)
async def broker_status(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    return await broker_service.get_broker_status(obj)


@router.post("/{broker_id}/test", response_model=BrokerTestResult)
async def test_broker(broker_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Broker, broker_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Broker not found")
    return await broker_service.test_broker_connection(obj)
