from enum import StrEnum
from http import HTTPStatus
from typing import Any

from pydantic import BaseModel, Field


class VliErrorCode(StrEnum):
    """
    Error codes of the virtual-lab backend service.
    """

    DATABASE_URI_NOT_SET = "DATABASE_URI_NOT_SET"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    ENTITY_NOT_CREATED = "ENTITY_NOT_CREATED"
    ENTITY_ALREADY_EXISTS = "ENTITY_ALREADY_EXISTS"
    ENTITY_ALREADY_UPDATED = "ENTITY_ALREADY_UPDATED"
    ENTITY_ALREADY_DELETED = "ENTITY_ALREADY_DELETED"
    INVALID_REQUEST = "INVALID_REQUEST"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    MULTIPLE_ENTITIES_FOUND = "MULTIPLE_ENTITIES_FOUND"
    DATABASE_ERROR = "DATABASE_ERROR"
    ENTITY_UPDATE__ERROR = "ENTITY_UPDATE__ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    NOT_ALLOWED_OP = "NOT_ALLOWED_OP"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    DATA_CONFLICT = "DATA_CONFLICT"
    FORBIDDEN_OPERATION = "FORBIDDEN_OPERATION"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


class VliError(Exception):
    """Base class for virtual-lab backend service exceptions."""

    message: str
    error_code: str
    http_status_code: HTTPStatus
    details: str | None
    data: dict[str, Any] | None

    def __init__(
        self,
        *,
        message: str,
        error_code: VliErrorCode,
        details: str | None = None,
        http_status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
        data: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, http_status_code)
        self.message = message
        self.error_code = error_code
        self.http_status_code = http_status_code
        self.details = details
        self.data = data

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f'{class_name}(message="{self.message}", error_code={self.error_code}, details={self.details}, http_status_code={self.http_status_code}) data={self.data}'


class VlmValidationError(BaseModel):
    error_code: str
    details: dict[str, str] = Field(
        ...,
        examples=[{"field": "error's description"}],
        description="A dictionary containing more details about the error. Keys are often field names, and values are the specific error messages.",
    )
