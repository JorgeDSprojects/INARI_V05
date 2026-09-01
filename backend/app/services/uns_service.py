from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uns import Asset, Cell, Line, Area, Site, Enterprise


async def build_uns_topic(asset: Asset, db: AsyncSession) -> str:
    cell = await db.get(Cell, asset.cell_id)
    line = await db.get(Line, cell.line_id)
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)

    parts = [
        enterprise.name,
        site.name,
        area.name,
        line.name,
        cell.name,
        asset.name,
        "_descriptive",
    ]
    return "/".join(p.replace(" ", "_") for p in parts)
