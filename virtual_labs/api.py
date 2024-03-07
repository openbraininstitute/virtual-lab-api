from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.cors import CORSMiddleware

from .core.exceptions.api_error import VliError, VliErrorCode
from .core.schemas import api
from .infrastructure.settings import settings
from .routes.labs import router as virtual_lab_router
from .routes.projects import router as project_router
from .routes.users import router as user_router

app = FastAPI(title=settings.APP_NAME)


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
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = {
        err.get("loc", (0, index))[1]: err.get(
            "msg", "Field value is invalid. Further details unavailable."
        )
        for index, err in enumerate(exc.errors())
    }
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            {"error_code": VliErrorCode.INVALID_REQUEST, "details": errors}
        ),
    )


if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.CORS_ORIGINS.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(project_router)
app.include_router(virtual_lab_router)
app.include_router(user_router)


@app.get("/")
def root() -> str:
    return "server is running."
