import sys

from loguru import logger
from sqlalchemy import create_engine, exc
from sqlalchemy.orm import Session, sessionmaker

from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from virtual_labs.infrastructure.settings import settings

from .models import Base

if settings.DATABASE_URI is None and "pytest" not in sys.modules:
    raise VlmError(
        "DATABASE_URI/DATABASE_URL is not set",
        error_code=VlmErrorCode.DATABASE_URI_NOT_SET,
    )


def init_db() -> Session:
    try:
        # TODO: remove this, it's only momentarily
        if "pytest" not in sys.modules:
            engine = create_engine(
                settings.DATABASE_URI.unicode_string(),
                echo=settings.DEBUG_DATABASE_ECHO,
            )
            session_local = sessionmaker(autoflush=False, autocommit=False, bind=engine)
            Base.metadata.create_all(engine)

            logger.info("✅ DB connected")
            return session_local
    except exc.ArgumentError:
        logger.error("⛔️ database connection failed, check the env variable")


session_local = init_db()


def default_session_factory():
    try:
        database = session_local()
        yield database
    finally:
        database.close()
