import asyncio
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any, Dict, Generator, Optional

import sentry_sdk
from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from httpx import AsyncClient
from loguru import logger
from redis.asyncio import Redis
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.cors import CORSMiddleware

from virtual_labs.core.exceptions.api_error import (
    VliError,
    VliErrorCode,
    VlmValidationError,
)
from virtual_labs.core.schemas import api
from virtual_labs.infrastructure.db.config import (
    close_db,
    default_session_factory,
    initialize_db,
)
from virtual_labs.infrastructure.db.config import (
    get_health_status as get_db_health_status,
)
from virtual_labs.infrastructure.kc.config import (
    get_health_status as get_kc_health_status,
)
from virtual_labs.infrastructure.redis import (
    get_health_status as get_redis_health_status,
)
from virtual_labs.infrastructure.redis import get_redis
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.transport.httpx import httpx_factory
from virtual_labs.routes.accounting import router as accounting_router
from virtual_labs.routes.bookmarks import router as bookmarks_router
from virtual_labs.routes.common import router as common_router
from virtual_labs.routes.invites import router as invite_router
from virtual_labs.routes.labs import router as virtual_lab_router
from virtual_labs.routes.notebooks import router as notebook_router
from virtual_labs.routes.payments import router as payments_router
from virtual_labs.routes.projects import router as project_router
from virtual_labs.routes.subscription import router as subscription_router
from virtual_labs.routes.user import router as user_router

_redis_client: Optional[Redis] = None


@asynccontextmanager  # type: ignore
async def lifespan(app: FastAPI) -> Generator[None, Any, None]:  # type: ignore
    global _redis_client
    _redis_client = await get_redis()
    await initialize_db()
    yield
    await close_db()
    if _redis_client is not None:
        await _redis_client.close()


sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
    environment=settings.DEPLOYMENT_ENV,
)

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    openapi_url=f"{settings.BASE_PATH}/openapi.json",
    docs_url=f"{settings.BASE_PATH}/docs",
)

origins = []
if settings.CORS_ORIGINS:
    for origin in settings.CORS_ORIGINS:
        origins.append(origin)

app.add_middleware(SentryAsgiMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=settings.APP_NAME,
        version="0.0.9",
        description="API description",
        routes=app.routes,
    )
    openapi_schema["components"]["schemas"][
        "HTTPValidationError"
    ] = VlmValidationError.model_json_schema()
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {"type": "http", "scheme": "bearer"},
        "OAuth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": f"https://{settings.KC_HOST}/realms/{settings.KC_REALM_NAME}/protocol/openid-connect/auth",
                    "tokenUrl": f"https://{settings.KC_HOST}/realms/{settings.KC_REALM_NAME}/protocol/openid-connect/token",
                    "scopes": {},
                }
            },
        },
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method["security"] = [
                {"bearerAuth": []},
                {"OAuth2": []},
            ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore

base_router = APIRouter(prefix=settings.BASE_PATH)


@app.exception_handler(VliError)
async def vli_exception_handler(request: Request, exception: VliError) -> JSONResponse:
    """
    this is will handle (format, standardize) all exceptions raised by the app
    any VliError raised anywhere in the app, will be captured by this handler
    and format it.
    """
    logger.error(f"{request.method} {request.url} failed: {repr(exception)}")

    return JSONResponse(
        status_code=int(exception.http_status_code),
        content=api.ErrorResponse(
            message=exception.message,
            error_code=VliErrorCode(exception.error_code),
            details=exception.details,
            data=exception.data,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = {}
    for index, err in enumerate(exc.errors()):
        loc = err.get("loc", (0, index))
        # Safely get the field name, using index as fallback if loc tuple is too short
        field_name = loc[1] if len(loc) > 1 else f"field_{index}"
        error_msg = err.get(
            "msg", "Field value is invalid. Further details unavailable."
        )
        errors[field_name] = error_msg

    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            {"error_code": VliErrorCode.INVALID_REQUEST, "details": errors}
        ),
    )


@base_router.get("/")
def root() -> str:
    return "Server is running."


@base_router.get("/health")
async def health(
    httpx_client: AsyncClient = Depends(httpx_factory),
    session: AsyncSession = Depends(default_session_factory),
) -> Dict[str, Any]:
    redis_client = await get_redis()
    db_task = asyncio.create_task(get_db_health_status(session))
    kc_task = asyncio.create_task(get_kc_health_status(httpx_client))
    redis_task = asyncio.create_task(get_redis_health_status(redis_client))

    await asyncio.gather(db_task, kc_task, redis_task)

    db_status = db_task.result()
    kc_status = kc_task.result()
    redis_status = redis_task.result()

    overall_status = "ok"
    if (
        db_status.get("status") != "ok"
        or kc_status.get("status") != "ok"
        or redis_status.get("status") != "ok"
    ):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "db": db_status,
        "kc": kc_status,
        "redis": redis_status,
    }


base_router.include_router(common_router)
base_router.include_router(project_router)
base_router.include_router(virtual_lab_router)
base_router.include_router(invite_router)
base_router.include_router(payments_router)
base_router.include_router(bookmarks_router)
base_router.include_router(accounting_router)
base_router.include_router(notebook_router)
base_router.include_router(subscription_router)
base_router.include_router(user_router)

app.include_router(base_router)
