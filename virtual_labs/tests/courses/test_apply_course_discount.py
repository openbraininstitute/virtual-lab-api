"""Tests for the apply-course-discount endpoint (POST /courses/{course_id}/discount)."""

from contextlib import contextmanager
from decimal import Decimal
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
async def test_apply_discount_defaults_to_course_window(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, vlab_id = draft_course
    await _set_course_dates(async_test_client, course_id)

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            json={"discount": "0.5"},
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["virtual_lab_id"] == vlab_id
    assert Decimal(data["discount"]) == Decimal("0.5")

    mock.assert_awaited_once()
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert str(kwargs["virtual_lab_id"]) == vlab_id
    assert kwargs["valid_from"].isoformat().startswith("2026-09-01")
    assert kwargs["valid_to"].isoformat().startswith("2026-12-15")


@pytest.mark.asyncio
async def test_apply_discount_with_explicit_window(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

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
    assert kwargs["valid_from"].isoformat().startswith("2026-01-01")
    assert kwargs["valid_to"].isoformat().startswith("2026-06-30")


# ──────────────────────────────────────────────────────────────────────
# Validation / errors
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("discount", ["0", "1.5", "-0.2"])
async def test_apply_discount_rejects_out_of_range(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
    discount: str,
) -> None:
    course_id, _ = draft_course

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            json={"discount": discount},
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 422
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_discount_rejects_inverted_window(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.post(
        f"/courses/{course_id}/discount",
        json={
            "discount": "0.5",
            "valid_from": "2026-06-30T00:00:00Z",
            "valid_to": "2026-01-01T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_apply_discount_requires_a_start(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """No explicit valid_from and the draft course has no start_date."""
    course_id, _ = draft_course

    with mock_create_discount() as mock:
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            json={"discount": "0.5"},
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 400
    assert "valid_from" in response.json()["message"]
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_discount_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    with mock_create_discount():
        response = await async_test_client.post(
            f"/courses/{uuid4()}/discount",
            json={"discount": "0.5", "valid_from": "2026-01-01T00:00:00Z"},
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_apply_discount_surfaces_accounting_error(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    await _set_course_dates(async_test_client, course_id)

    error = AccountingError(
        message="accounting boom",
        type=AccountingErrorValue.CREATE_VIRTUAL_LAB_DISCOUNT_ERROR,
    )
    with patch(_DISCOUNT_TARGET, new_callable=AsyncMock, side_effect=error):
        response = await async_test_client.post(
            f"/courses/{course_id}/discount",
            json={"discount": "0.5"},
            headers=SERVICE_ADMIN_HEADERS,
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_apply_discount_forbidden_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.post(
        f"/courses/{course_id}/discount",
        json={"discount": "0.5", "valid_from": "2026-01-01T00:00:00Z"},
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
        json={"discount": "0.5", "valid_from": "2026-01-01T00:00:00Z"},
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401
