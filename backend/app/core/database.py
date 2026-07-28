from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)


async def init_db() -> None:
    """Create the engine and execute PRAGMA statements for SQLite."""
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
