from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uns import Asset, Cell, Line, Area, Site, Enterprise


def _slug(s: str) -> str:
    """Replace spaces with underscores (preserve case)."""
    return s.replace(" ", "_")


async def build_uns_topic(asset: Asset, db: AsyncSession, suffix: str = "_descriptive") -> str:
    cell = await db.get(Cell, asset.cell_id)
    line = await db.get(Line, cell.line_id)
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, line.name, cell.name, asset.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_cell_topic(cell: Cell, db: AsyncSession, suffix: str = "_descriptive") -> str:
    line = await db.get(Line, cell.line_id)
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, line.name, cell.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_line_topic(line: Line, db: AsyncSession, suffix: str = "_descriptive") -> str:
    area = await db.get(Area, line.area_id)
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, line.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_area_topic(area: Area, db: AsyncSession, suffix: str = "_descriptive") -> str:
    site = await db.get(Site, area.site_id)
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, area.name, suffix]
    return "/".join(_slug(p) for p in parts)


async def build_site_topic(site: Site, db: AsyncSession, suffix: str = "_descriptive") -> str:
    enterprise = await db.get(Enterprise, site.enterprise_id)
    parts = [enterprise.name, site.name, suffix]
    return "/".join(_slug(p) for p in parts)


def build_enterprise_topic(enterprise: Enterprise, suffix: str = "_descriptive") -> str:
    parts = [enterprise.name, suffix]
    return "/".join(_slug(p) for p in parts)
