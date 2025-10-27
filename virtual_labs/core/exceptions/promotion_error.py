"""
Promotion code specific exceptions.
Defines custom exceptions for promotion code operations and validation failures.
"""

from datetime import datetime
from http import HTTPStatus
from typing import Any, Optional
from uuid import UUID

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode


class PromotionError(VliError):
    """Base exception for all promotion-related errors."""

    def __init__(
        self,
        message: str,
        http_status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
        error_code: VliErrorCode = VliErrorCode.INVALID_REQUEST,
        details: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            http_status_code=http_status_code,
            error_code=error_code,
            details=details,
            data=data,
        )


class PromotionNotFoundError(PromotionError):
    """Raised when a promotion code does not exist."""

    def __init__(self, code: str) -> None:
        super().__init__(
            message=f"Promotion code '{code}' not found",
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            data={"code": code},
        )


class PromotionExpiredError(PromotionError):
    """Raised when a promotion code has expired."""

    def __init__(self, code: str, expired_at: datetime) -> None:
        super().__init__(
            message=f"Promotion code '{code}' has expired",
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.INVALID_REQUEST,
            data={"code": code, "expired_at": expired_at.isoformat()},
        )


class PromotionNotActiveError(PromotionError):
    """Raised when a promotion code is not active."""

    def __init__(self, code: str) -> None:
        super().__init__(
            message=f"Promotion code '{code}' is not active",
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.INVALID_REQUEST,
            data={"code": code},
        )


class PromotionNotYetValidError(PromotionError):
    """Raised when a promotion code validity period has not started yet."""

    def __init__(self, code: str, valid_from: datetime) -> None:
        super().__init__(
            message=f"Promotion code '{code}' is not yet valid",
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.INVALID_REQUEST,
            data={"code": code, "valid_from": valid_from.isoformat()},
        )


class PromotionAlreadyUsedError(PromotionError):
    """Raised when a user has already used the promotion code in the current period."""

    def __init__(self, code: str, user_id: UUID, virtual_lab_id: UUID) -> None:
        super().__init__(
            message=f"You have already used promotion code '{code}' for this virtual lab",
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.INVALID_REQUEST,
            data={
                "code": code,
                "virtual_lab_id": str(virtual_lab_id),
            },
        )


class PromotionUsageLimitReachedError(PromotionError):
    """Raised when a promotion code has reached its total usage limit."""

    def __init__(self, code: str, max_uses: int) -> None:
        super().__init__(
            message=f"Promotion code '{code}' has reached its usage limit",
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.LIMIT_EXCEEDED,
            data={"code": code, "max_uses": max_uses},
        )


class PromotionRedemptionError(PromotionError):
    """Raised when promotion code redemption fails."""

    def __init__(
        self, message: str, code: str, data: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(
            message=message,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.SERVER_ERROR,
            data={"code": code, **(data or {})},
        )


class PromotionAccountingError(PromotionError):
    """Raised when accounting system integration fails during redemption."""

    def __init__(
        self, message: str, code: str, virtual_lab_id: UUID, details: Any
    ) -> None:
        super().__init__(
            message=f"Failed to credit virtual lab: {message}",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            data={
                "code": code,
                "virtual_lab_id": str(virtual_lab_id),
                "original_error": message,
            },
            details=details,
        )


class PromotionCodeAlreadyExistsError(PromotionError):
    """Raised when attempting to create a promotion code that already exists."""

    def __init__(self, code: str) -> None:
        super().__init__(
            message=f"Promotion code '{code}' already exists",
            http_status_code=HTTPStatus.CONFLICT,
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            data={"code": code},
        )


class PromotionInvalidOperationError(PromotionError):
    """Raised when an invalid operation is attempted on a promotion code."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(
            message=message,
            http_status_code=HTTPStatus.BAD_REQUEST,
            error_code=VliErrorCode.INVALID_REQUEST,
            data={"code": code},
        )
