import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, AsyncIterator, Dict, Optional, Self

import asyncssh
from asyncssh import SSHClientConnection, SSHListener
from loguru import logger
from sqlalchemy import text
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
    _ssh_tunnel: Optional[SSHListener] = None
    _ssh_conn: Optional[SSHClientConnection] = None

    def __init__(self, host: str, options: Dict[str, Any] = {}) -> None:
        self._engine = None
        self._session_maker = None
        self._ssh_conn = None
        self._ssh_tunnel = None
        self._host = host
        self._options = options

    async def resolve(
        self,
    ) -> Self:
        db_uri = self._host
        if settings.USE_SSH_TUNNEL:
            self._ssh_conn = await asyncssh.connect(
                host=settings.SSH_HOST,
                port=settings.SSH_PORT,
                username=settings.SSH_USERNAME,
                client_keys=[settings.SSH_PRIVATE_KEY_PATH],
                known_hosts=None,
            )
            self._ssh_tunnel = await self._ssh_conn.forward_local_port(
                "", 0, settings.POSTGRES_HOST, settings.POSTGRES_PORT
            )
            local_port = self._ssh_tunnel.get_port()
            db_uri = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@localhost:{local_port}/{settings.POSTGRES_DB}"

        # Create engine and session maker
        self._engine = create_async_engine(db_uri, **self._options)

        self._session_maker = async_sessionmaker(
            autoflush=False, autocommit=False, bind=self._engine
        )
        logger.info(
            "✅ DB connected"
            + (" via SSH tunnel" if getattr(settings, "USE_SSH_TUNNEL", False) else "")
        )
        return self

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None

        if self._ssh_tunnel is not None:
            self._ssh_tunnel.close()
            self._ssh_tunnel = None

        if self._ssh_conn is not None:
            self._ssh_conn.close()
            await self._ssh_conn.wait_closed()
            self._ssh_conn = None

        logger.info("✅ DB disconnected")

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
            raise Exception("SessionPool not initialized. Call initialize() first.")

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


async def initialize_db() -> None:
    """Initialize the database connection - call this during application startup"""
    global session_pool
    if session_pool is not None:
        session_pool = await session_pool.resolve()


async def close_db() -> None:
    """Close the database connection - call this during application shutdown"""
    global session_pool
    if session_pool is not None:
        await session_pool.close()


async def default_session_factory() -> AsyncGenerator[AsyncSession, None]:
    async with session_pool.session() as session:
        yield session


async def get_health_status(session: AsyncSession) -> Dict[str, str | None]:
    """Check database connection health."""
    try:
        await session.execute(text("SELECT 1"))

        version_result = await session.execute(text("SELECT version()"))
        version_info = version_result.scalar_one_or_none()

        return {
            "status": "ok",
            "message": "healthy",
            "version": version_info,
        }
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {
            "status": "degraded",
            "message": f"Database connection failed: {str(e)}",
            "version": None,
        }
