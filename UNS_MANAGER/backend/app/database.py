from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    from app.models import uns  # noqa: F401
    from app.models import broker  # noqa: F401
    from app.models import node_type  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent column additions for existing databases
        await conn.execute(text(
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS "
            "node_type_id VARCHAR(36) REFERENCES node_types(id) ON DELETE SET NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS "
            "last_published_at TIMESTAMPTZ"
        ))
        # Multi-level payload columns (idempotent)
        await conn.execute(text("ALTER TABLE assets ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE enterprises ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE enterprises ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE enterprises ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE sites ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE sites ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE sites ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE lines ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE lines ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE lines ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE cells ADD COLUMN IF NOT EXISTS descriptive_payload JSONB"))
        await conn.execute(text("ALTER TABLE cells ADD COLUMN IF NOT EXISTS informative_payload JSONB"))
        await conn.execute(text("ALTER TABLE cells ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMPTZ"))
