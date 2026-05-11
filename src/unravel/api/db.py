"""Async SQLAlchemy engine + session for the FastAPI app.

Phase 0 keeps it minimal: one engine, one session-per-request dep, no pool tuning.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://unravel:unravel@localhost:5544/unravel"
)


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(database_url(), pool_pre_ping=True)

async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
