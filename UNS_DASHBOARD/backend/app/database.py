from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

historian_engine = create_async_engine(settings.historian_database_url, echo=False, future=True)
HistorianSessionLocal = async_sessionmaker(historian_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def get_historian_db() -> AsyncSession:
    async with HistorianSessionLocal() as session:
        yield session


async def create_tables() -> None:
    from app.models import dashboard  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
