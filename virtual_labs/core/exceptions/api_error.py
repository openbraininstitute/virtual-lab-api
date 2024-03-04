from enum import IntEnum
from http import HTTPStatus


class VlmErrorCode(IntEnum):
    """
    Error codes of the virtual-lab backend service.
    """

    DATABASE_URI_NOT_SET = 1
    ENTITY_NOT_FOUND = 2


class VlmError(Exception):
    """Base class for virtual-lab backend service exceptions."""

    message: str
    error_code: int
    http_status_code: HTTPStatus

    def __init__(
        self,
        message: str,
        error_code: VlmErrorCode,
        http_status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ):
        super().__init__(message, error_code, http_status_code)
        self.message = message
        self.error_code = error_code
        self.http_status_code = http_status_code

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f'{class_name}(message="{self.message}", error_code={self.error_code}, http_status_code={self.http_status_code})'
