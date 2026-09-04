from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.uns import Enterprise, Site, Area, Line, Cell, Asset
from app.models.uns import _uuid
from app.services.mqtt_service import publish_descriptive
from app.services.uns_service import build_uns_topic

logger = logging.getLogger(__name__)

LEVEL_ORDER = ["enterprise", "site", "area", "line", "cell", "asset"]


async def _copy_sites(site: Site, new_enterprise_id: str, db: AsyncSession) -> tuple[str, int]:
    new_id = _uuid()
    new_site = Site(id=new_id, enterprise_id=new_enterprise_id, name=site.name, description=site.description)
    db.add(new_site)
    await db.flush()
    count = 1
    for area in site.areas:
        _, child_count = await _copy_areas(area, new_site.id, db)
        count += child_count
    return new_id, count


async def _copy_areas(area: Area, new_site_id: str, db: AsyncSession) -> tuple[str, int]:
    new_id = _uuid()
    new_area = Area(id=new_id, site_id=new_site_id, name=area.name, description=area.description)
    db.add(new_area)
    await db.flush()
    count = 1
    for line in area.lines:
        _, child_count = await _copy_lines(line, new_area.id, db)
        count += child_count
    return new_id, count


async def _copy_lines(line: Line, new_area_id: str, db: AsyncSession) -> tuple[str, int]:
    new_id = _uuid()
    new_line = Line(id=new_id, area_id=new_area_id, name=line.name, description=line.description)
    db.add(new_line)
    await db.flush()
    count = 1
    for cell in line.cells:
        _, child_count = await _copy_cells(cell, new_line.id, db)
        count += child_count
    return new_id, count


async def _copy_cells(cell: Cell, new_line_id: str, db: AsyncSession) -> tuple[str, int]:
    new_id = _uuid()
    new_cell = Cell(id=new_id, line_id=new_line_id, name=cell.name, description=cell.description)
    db.add(new_cell)
    await db.flush()
    count = 1
    for asset in cell.assets:
        new_asset = Asset(
            id=_uuid(), cell_id=new_cell.id,
            name=asset.name, description=asset.description,
            descriptive_payload=asset.descriptive_payload,
            node_type_id=asset.node_type_id,
        )
        db.add(new_asset)
        count += 1
    return new_id, count


async def copy_subtree(
    source_id: str, source_level: str, target_parent_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Deep-copy a subtree under a new parent. Returns new root id and node count."""
    if source_level == "site":
        result = await db.execute(
            select(Site).where(Site.id == source_id)
            .options(selectinload(Site.areas).selectinload(Area.lines).selectinload(Line.cells).selectinload(Cell.assets))
        )
        site = result.scalar_one_or_none()
        if not site:
            raise ValueError("Source site not found")
        new_id, count = await _copy_sites(site, target_parent_id, db)
        await db.commit()
        return {"new_root_id": new_id, "node_count": count}

    elif source_level == "area":
        result = await db.execute(
            select(Area).where(Area.id == source_id)
            .options(selectinload(Area.lines).selectinload(Line.cells).selectinload(Cell.assets))
        )
        area = result.scalar_one_or_none()
        if not area:
            raise ValueError("Source area not found")
        new_id, count = await _copy_areas(area, target_parent_id, db)
        await db.commit()
        return {"new_root_id": new_id, "node_count": count}

    elif source_level == "line":
        result = await db.execute(
            select(Line).where(Line.id == source_id)
            .options(selectinload(Line.cells).selectinload(Cell.assets))
        )
        line = result.scalar_one_or_none()
        if not line:
            raise ValueError("Source line not found")
        new_id, count = await _copy_lines(line, target_parent_id, db)
        await db.commit()
        return {"new_root_id": new_id, "node_count": count}

    elif source_level == "cell":
        result = await db.execute(
            select(Cell).where(Cell.id == source_id)
            .options(selectinload(Cell.assets))
        )
        cell = result.scalar_one_or_none()
        if not cell:
            raise ValueError("Source cell not found")
        new_id, count = await _copy_cells(cell, target_parent_id, db)
        await db.commit()
        return {"new_root_id": new_id, "node_count": count}

    raise ValueError(f"Unsupported source level: {source_level}")


async def move_subtree(
    source_id: str, source_level: str, target_parent_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Move a node to a new parent by updating its FK. Single transaction."""
    if source_level == "site":
        obj = await db.get(Site, source_id)
        if not obj:
            raise ValueError("Source site not found")
        obj.enterprise_id = target_parent_id
    elif source_level == "area":
        obj = await db.get(Area, source_id)
        if not obj:
            raise ValueError("Source area not found")
        obj.site_id = target_parent_id
    elif source_level == "line":
        obj = await db.get(Line, source_id)
        if not obj:
            raise ValueError("Source line not found")
        obj.area_id = target_parent_id
    elif source_level == "cell":
        obj = await db.get(Cell, source_id)
        if not obj:
            raise ValueError("Source cell not found")
        obj.line_id = target_parent_id
    elif source_level == "asset":
        obj = await db.get(Asset, source_id)
        if not obj:
            raise ValueError("Source asset not found")
        obj.cell_id = target_parent_id
    else:
        raise ValueError(f"Unsupported source level: {source_level}")
    await db.commit()
    return {"moved_root_id": source_id, "node_count": 1}


async def publish_subtree(root_id: str, root_level: str, db: AsyncSession) -> dict[str, Any]:
    """Publish all assets in a subtree to EMQX. Returns published/failed counts."""
    published = 0
    failed = 0

    async def pub_asset(asset: Asset) -> None:
        nonlocal published, failed
        if not asset.descriptive_payload:
            return
        try:
            topic = await build_uns_topic(asset, db)
            asset.uns_topic = topic
            publish_descriptive(topic, asset.descriptive_payload)
            asset.last_published_at = datetime.now(timezone.utc)
            published += 1
        except Exception as exc:
            logger.error("Failed to publish asset %s: %s", asset.id, exc)
            failed += 1

    if root_level == "asset":
        asset = await db.get(Asset, root_id)
        if asset:
            await pub_asset(asset)
    elif root_level == "cell":
        result = await db.execute(select(Asset).where(Asset.cell_id == root_id))
        for asset in result.scalars().all():
            await pub_asset(asset)
    elif root_level == "line":
        result = await db.execute(
            select(Cell).where(Cell.line_id == root_id).options(selectinload(Cell.assets))
        )
        for cell in result.scalars().all():
            for asset in cell.assets:
                await pub_asset(asset)
    elif root_level == "area":
        result = await db.execute(
            select(Line).where(Line.area_id == root_id)
            .options(selectinload(Line.cells).selectinload(Cell.assets))
        )
        for line in result.scalars().all():
            for cell in line.cells:
                for asset in cell.assets:
                    await pub_asset(asset)
    elif root_level == "site":
        result = await db.execute(
            select(Area).where(Area.site_id == root_id)
            .options(selectinload(Area.lines).selectinload(Line.cells).selectinload(Cell.assets))
        )
        for area in result.scalars().all():
            for line in area.lines:
                for cell in line.cells:
                    for asset in cell.assets:
                        await pub_asset(asset)
    elif root_level == "enterprise":
        result = await db.execute(
            select(Site).where(Site.enterprise_id == root_id)
            .options(selectinload(Site.areas).selectinload(Area.lines).selectinload(Line.cells).selectinload(Cell.assets))
        )
        for site in result.scalars().all():
            for area in site.areas:
                for line in area.lines:
                    for cell in line.cells:
                        for asset in cell.assets:
                            await pub_asset(asset)

    await db.commit()
    return {"published": published, "failed": failed}
