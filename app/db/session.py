from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.settings import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=30,
    max_overflow=60,
    pool_timeout=5,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=False,
    connect_args={"server_settings": {"application_name": "rarehandle-bot"}},
)

worker_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
    poolclass=NullPool,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
WorkerSessionLocal = async_sessionmaker(worker_engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engines() -> None:
    await engine.dispose()
    await worker_engine.dispose()
