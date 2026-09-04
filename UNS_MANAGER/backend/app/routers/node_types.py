from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.node_type import NodeType
from app.schemas.node_type import (
    NodeTypeCreate,
    NodeTypeRead,
    NodeTypeUpdate,
    ValidationResult,
)
from app.services import node_type_service

router = APIRouter(prefix="/node-types", tags=["Node Types"])


class ValidateBody(BaseModel):
    payload: dict[str, Any]


@router.get("/", response_model=list[NodeTypeRead])
async def list_node_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(NodeType).order_by(NodeType.name))
    return result.scalars().all()


@router.post("/", response_model=NodeTypeRead, status_code=status.HTTP_201_CREATED)
async def create_node_type(body: NodeTypeCreate, db: AsyncSession = Depends(get_db)):
    obj = NodeType(
        name=body.name,
        description=body.description,
        json_schema=body.json_schema,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{node_type_id}", response_model=NodeTypeRead)
async def get_node_type(node_type_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    return obj


@router.put("/{node_type_id}", response_model=NodeTypeRead)
async def update_node_type(
    node_type_id: str, body: NodeTypeUpdate, db: AsyncSession = Depends(get_db)
):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{node_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node_type(node_type_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    await db.delete(obj)
    await db.commit()


@router.post("/{node_type_id}/validate", response_model=ValidationResult)
async def validate_payload(
    node_type_id: str,
    body: ValidateBody,
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(NodeType, node_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Node type not found")
    valid, errors = node_type_service.validate_payload(obj.json_schema, body.payload)
    return ValidationResult(valid=valid, errors=errors)
