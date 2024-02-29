from fastapi import FastAPI, Request, responses
from loguru import logger
from starlette.middleware.cors import CORSMiddleware

from .core.exceptions.api_error import VlmError, VlmErrorCode
from .core.schemas import api
from .infrastructure.settings import settings
from .routes.projects import router as project_router
from .routes.users import router as user_router

app = FastAPI(title=settings.APP_NAME)


@app.exception_handler(VlmError)
async def vlm_exception_handler(request: Request, exception: VlmError):
    """
    this is will handle (format, standardize) all exceptions raised by the app
    any VlmError raised anywhere in the app, will be captured by this handler
    and format it.
    """
    logger.error(f"{request.method} {request.url} failed: {repr(exception)}")

    return responses.JSONResponse(
        status_code=int(exception.http_status_code),
        content=api.ErrorResponse(
            message=exception.message,
            error_code=VlmErrorCode(exception.error_code),
        ).model_dump(),
    )


if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(project_router)
app.include_router(user_router)


@app.get("/")
def root() -> str:
    return "📡 server is running."
