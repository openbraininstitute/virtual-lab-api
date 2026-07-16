import sentry_sdk

from virtual_labs.infrastructure.settings import settings


def init_sentry() -> None:
    """Initialize the Sentry SDK.

    The SDK auto-enables the FastAPI, Starlette, SQLAlchemy, asyncpg, redis
    and loguru integrations, so API errors, DB spans and ``logger.exception``
    calls are captured without an explicit ``integrations`` list.
    """
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.DEPLOYMENT_ENV,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profile_session_sample_rate=settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE,
        profile_lifecycle="trace",
    )
