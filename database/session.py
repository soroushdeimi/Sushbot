"""Database session management """

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from config.settings import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _normalize_database_url(url: str) -> str:
    """Ensure database URL uses asyncpg driver."""
    parsed = urlparse(url)
    scheme = parsed.scheme

    if scheme == "postgresql":
        scheme = "postgresql+asyncpg"
    elif scheme == "postgres":
        scheme = "postgresql+asyncpg"
    elif "+" in scheme and "asyncpg" not in scheme:
        base = scheme.split("+")[0]
        scheme = f"{base}+asyncpg"

    return urlunparse(parsed._replace(scheme=scheme))


_normalized_url = _normalize_database_url(settings.database_url)

engine: AsyncEngine = create_async_engine(
    _normalized_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Base for declarative models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    from database.models import Base  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()

