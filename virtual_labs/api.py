from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any, Generator, Optional

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from loguru import logger
from redis.asyncio import Redis
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from starlette.middleware.cors import CORSMiddleware

from virtual_labs.core.exceptions.api_error import (
    VliError,
    VliErrorCode,
    VlmValidationError,
)
from virtual_labs.core.schemas import api
from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.infrastructure.redis import get_redis
from virtual_labs.infrastructure.settings import settings
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
    yield
    if session_pool._engine is not None:
        await session_pool.close()
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


# TODO: add a proper health check logic, see https://pypi.org/project/fastapi-health/.
@base_router.get("/health")
def health() -> str:
    return "OK"


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
