"""Tests for the apply-course-discount endpoint (POST /courses/{course_id}/discount)."""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Iterator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.models import CreateDiscountResponse
from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.courses.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.utils import get_headers

_DISCOUNT_TARGET = (
    "virtual_labs.usecases.course.apply_course_discount."
    "accounting_cases.create_virtual_lab_discount"
)


@contextmanager
def mock_create_discount() -> Iterator[AsyncMock]:
    """Patch the accounting discount call; echoes its args into the response."""

    async def _echo(**kwargs: Any) -> CreateDiscountResponse:
        valid_to = kwargs["valid_to"]
        return CreateDiscountResponse.model_validate(
            {
                "message": "created",
                "data": {
                    "id": 1,
                    "vlab_id": str(kwargs["virtual_lab_id"]),
                    "discount": str(kwargs["discount"]),
                    "valid_from": kwargs["valid_from"].isoformat(),
                    "valid_to": valid_to.isoformat() if valid_to is not None else None,
                },
            }
        )

    with patch(_DISCOUNT_TARGET, new_callable=AsyncMock, side_effect=_echo) as m:
        yield m


async def _set_course_dates(async_test_client: AsyncClient, course_id: str) -> None:
    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2026-09-01T00:00:00Z",
            "end_date": "2026-12-15T00:00:00Z",
            "last_drop_date": "2026-09-14T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )
    assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Happy path
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_discount_uses_course_window_and_settings_amount(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, vlab_id = draft_course
    await _set_course_dates(async_test_client, course_id)

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["virtual_lab_id"] == vlab_id
    # The amount is fixed by settings, not caller-supplied.
    assert Decimal(data["discount"]) == settings.COURSE_COMPUTE_DISCOUNT

    mock.assert_awaited_once()
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert str(kwargs["virtual_lab_id"]) == vlab_id
    assert kwargs["discount"] == settings.COURSE_COMPUTE_DISCOUNT
    assert kwargs["valid_from"].isoformat().startswith("2026-09-01")
    assert kwargs["valid_to"].isoformat().startswith("2026-12-15")


@pytest.mark.asyncio
async def test_apply_discount_sends_timezone_aware_utc(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """The window sent upstream must be timezone-aware and in UTC (offset 0)."""
    course_id, _ = draft_course
    await _set_course_dates(async_test_client, course_id)

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    for key in ("valid_from", "valid_to"):
        dt = kwargs[key]
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_apply_discount_ignores_request_body(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """The API accepts no body — any fields sent are ignored, the course
    dates and the settings amount are always used."""
    course_id, _ = draft_course
    await _set_course_dates(async_test_client, course_id)

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            json={
                "discount": "0.25",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": "2026-06-30T00:00:00Z",
            },
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["discount"] == settings.COURSE_COMPUTE_DISCOUNT
    assert kwargs["valid_from"].isoformat().startswith("2026-09-01")
    assert kwargs["valid_to"].isoformat().startswith("2026-12-15")


# ──────────────────────────────────────────────────────────────────────
# Validation / errors
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_discount_requires_course_dates(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """The draft course has no start_date / end_date set."""
    course_id, _ = draft_course

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 400
    assert "start_date" in response.json()["message"]
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_discount_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    with mock_create_discount():
        response = await async_test_client.post(
            f"/courses/{uuid4()}/discount",
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [
        (None, 503),  # connection error / timeout
        (HTTPStatus.REQUEST_TIMEOUT, 503),  # retryable upstream signal
        (HTTPStatus.TOO_MANY_REQUESTS, 503),
        (HTTPStatus.BAD_REQUEST, 400),  # accounting rejected the payload
        (HTTPStatus.UNPROCESSABLE_ENTITY, 400),
        (HTTPStatus.INTERNAL_SERVER_ERROR, 502),  # accounting outage
        (HTTPStatus.BAD_GATEWAY, 502),
    ],
)
async def test_apply_discount_maps_accounting_error_to_contract(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
    upstream_status: HTTPStatus | None,
    expected_status: int,
) -> None:
    course_id, _ = draft_course
    await _set_course_dates(async_test_client, course_id)

    error = AccountingError(
        message="vlab_id 123 already has a discount: <internal accounting detail>",
        type=AccountingErrorValue.CREATE_VIRTUAL_LAB_DISCOUNT_ERROR,
        http_status_code=upstream_status,
    )
    with patch(_DISCOUNT_TARGET, new_callable=AsyncMock, side_effect=error):
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == expected_status
    body = response.json()
    # The raw upstream message must never leak to the caller.
    assert "internal accounting detail" not in body["message"]
    assert "accounting service" in body["message"]


@pytest.mark.asyncio
async def test_apply_discount_forbidden_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.post(
        f"/courses/{course_id}/discount",
        headers=get_headers(),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_apply_discount_unauthenticated(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.post(
        f"/courses/{course_id}/discount",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401
