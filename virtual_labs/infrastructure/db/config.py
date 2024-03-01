import sys
from typing import Any, Generator

from loguru import logger
from sqlalchemy import Engine, create_engine, exc
from sqlalchemy.orm import Session, sessionmaker

from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from virtual_labs.infrastructure.settings import settings

from .models import Base

if settings.DATABASE_URI is None and "pytest" not in sys.modules:
    raise VlmError(
        "DATABASE_URI/DATABASE_URL is not set",
        error_code=VlmErrorCode.DATABASE_URI_NOT_SET,
    )


def init_db() -> Engine:
    try:
        engine = create_engine(
            settings.DATABASE_URI.unicode_string(),
            echo=settings.DEBUG_DATABASE_ECHO,
        )
        Base.metadata.create_all(engine)

        logger.info("✅ DB connected")
        return engine
    except exc.ArgumentError:
        logger.error("⛔️ database connection failed, check the env variable")
        raise


engine: Engine = init_db()
session_factory: sessionmaker[Session] = sessionmaker(
    autoflush=False, autocommit=False, bind=engine
)


def default_session_factory() -> Generator[Session, Any, None]:
    try:
        database = session_factory()
        yield database
    finally:
        database.close()
