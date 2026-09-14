"""Apply / reverse the course pro discount on a course's virtual lab.

Shared by course creation and update: both mirror the discount validity to
the course window (``start_date`` → ``end_date``). Accounting has no
"update discount" endpoint, so a new discount is recorded each time and the
latest one wins.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from decimal import Decimal
from http import HTTPStatus
from uuid import UUID

from loguru import logger

from virtual_labs.core.exceptions.accounting_error import AccountingError
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.settings import settings
from virtual_labs.usecases import accounting as accounting_cases


def as_utc(value: datetime | None) -> datetime | None:
    """Coerce a datetime to UTC-aware (accounting requires AwareDatetime)."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def apply_pro_discount(
    virtual_lab_id: UUID,
    *,
    valid_from: datetime,
    valid_to: datetime | None,
    failure_message: str,
) -> None:
    """Record the pro discount on the virtual lab, aborting on failure.

    The discount validity mirrors the course window: ``valid_from`` is the
    course start date and ``valid_to`` the course end date.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return

    try:
        await accounting_cases.create_virtual_lab_discount(
            virtual_lab_id=virtual_lab_id,
            discount=settings.COURSE_PRO_DISCOUNT,
            valid_from=as_utc(valid_from) or datetime.now(timezone.utc),
            valid_to=as_utc(valid_to),
        )
    except AccountingError as err:
        logger.error(
            f"Failed to apply pro discount for virtual lab {virtual_lab_id}: {err}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=err.http_status_code or HTTPStatus.INTERNAL_SERVER_ERROR,
            message=failure_message,
        ) from err
    except Exception as err:
        logger.exception(
            f"Unexpected error applying pro discount for virtual lab "
            f"{virtual_lab_id}: {err}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=failure_message,
        ) from err


def make_pro_discount_compensation(
    virtual_lab_id: UUID,
    *,
    discount: Decimal,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> Callable[[], Awaitable[None]]:
    """Undo a pro-discount write by recording a superseding discount.

    Accounting has no "delete discount" endpoint, so compensation records a
    fresh discount: ``0`` to cancel a just-applied discount (course creation),
    or the previous rate/window to roll a failed update back.
    """

    async def _undo() -> None:
        try:
            await accounting_cases.create_virtual_lab_discount(
                virtual_lab_id=virtual_lab_id,
                discount=discount,
                valid_from=as_utc(valid_from) or datetime.now(timezone.utc),
                valid_to=as_utc(valid_to),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                f"Failed to compensate pro discount for virtual lab "
                f"{virtual_lab_id}; reconcile manually: {exc}"
            )

    return _undo
