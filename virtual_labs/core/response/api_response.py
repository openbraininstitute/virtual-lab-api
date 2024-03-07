from http import HTTPStatus
from typing import Generic, TypeVar

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

T = TypeVar("T")


class VliResponse(Generic[T]):
    @staticmethod
    def new(
        *,
        message: str,
        data: T | None = None,
        http_status_code: HTTPStatus = HTTPStatus.OK,
    ) -> Response:
        return JSONResponse(
            status_code=http_status_code,
            content=jsonable_encoder({"message": message, "data": data}),
        )
