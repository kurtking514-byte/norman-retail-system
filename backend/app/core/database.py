from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    poolclass=NullPool if "asyncpg" in settings.DATABASE_URL else None,
    connect_args={"statement_cache_size": 0} if "asyncpg" in settings.DATABASE_URL else {},
)


async def init_db() -> None:
    """Create the engine and execute driver-specific init."""
    if engine.dialect.name == "sqlite":
        async with engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
    # Import Base and all models to ensure they are registered
    from app.models.base import Base  # noqa: F811

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency that yields an AsyncSession."""
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()

