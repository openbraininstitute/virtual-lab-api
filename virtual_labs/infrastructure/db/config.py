import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Generator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.settings import settings

if settings.DATABASE_URI is None and "pytest" not in sys.modules:
    raise VliError(
        "DATABASE_URI/DATABASE_URL is not set",
        error_code=VliErrorCode.DATABASE_URI_NOT_SET,
    )


class DatabaseSessionPool:
    _engine: AsyncEngine | None
    _session_maker: async_sessionmaker[AsyncSession] | None

    def __init__(self, host: str, options: Dict[str, Any] = {}) -> None:
        self._engine = create_async_engine(host, **options)
        self._session_maker = async_sessionmaker(
            autoflush=False, autocommit=False, bind=self._engine
        )
        logger.info("✅ DB connected")

    async def close(self) -> None:
        if (self._engine) is None:
            raise Exception("SessionPool not initialized")
        await self._engine.dispose()
        self._engine = None
        self._session_maker = None

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise Exception("SessionPool not initialized")

        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._session_maker is None:
            raise Exception("SessionPool not initialized")

        session = self._session_maker()

        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


session_pool = DatabaseSessionPool(
    host=settings.DATABASE_URI.unicode_string(),
    options={
        "echo": settings.DEBUG_DATABASE_ECHO,
    },
)


async def default_session_factory() -> Generator[AsyncSession, Any, None]:  # type: ignore
    async with session_pool.session() as session:
        yield session
