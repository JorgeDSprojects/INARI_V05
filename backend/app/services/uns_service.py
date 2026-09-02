from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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


async def clear_subtree_retained(topic_prefix: str, db: AsyncSession) -> None:
    """Clear all retained MQTT messages under *topic_prefix* using the EMQX REST API.

    Queries EMQX for every retained topic matching ``topic_prefix/#``, then
    publishes an empty payload (retain=True) on each one so that connected
    clients (e.g. MQTT Explorer) receive the deletion notification.

    Falls back silently if no broker is configured or the API is unreachable.
    """
    from app.models.broker import Broker
    from app.services.broker_service import list_retained_topics_by_prefix
    from app.services.mqtt_service import clear_retained

    # Get the first configured broker (same as existing publish logic)
    result = await db.execute(select(Broker).order_by(Broker.label).limit(1))
    broker = result.scalar_one_or_none()
    if not broker:
        return

    topics = await list_retained_topics_by_prefix(broker, topic_prefix)
    for t in topics:
        try:
            clear_retained(t)
        except Exception:
            pass
