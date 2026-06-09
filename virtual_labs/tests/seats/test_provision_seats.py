"""Tests for the provision-seats endpoint (POST /seats/provision)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.utils import get_headers


def _provision_payload(course_id: str, number_of_seats: int = 3) -> dict:
    return {
        "course_id": course_id,
        "number_of_seats": number_of_seats,
    }


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provision_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    body = _provision_payload(course_for_seats, number_of_seats=2)

    with patch(
        "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
    ) as mock_top_up:
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["seats"]) == 2
    assert data["total_credits_topped_up"] == 400.0
    batch_ids = set()
    for seat in data["seats"]:
        assert "course_id" in seat
        assert seat["is_consumed"] is False
        assert seat["active_project_id"] is None
        assert "batch_id" in seat
        batch_ids.add(seat["batch_id"])
    # All seats in the same provision call share one batch_id
    assert len(batch_ids) == 1


@pytest.mark.asyncio
async def test_provision_seats_calls_accounting_top_up(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    body = _provision_payload(course_for_seats, number_of_seats=5)

    with (
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
        patch(
            "virtual_labs.usecases.seat.provision_seats.settings.ACCOUNTING_BASE_URL",
            "http://accounting:8000",
        ),
    ):
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    mock_top_up.assert_awaited_once()
    call_kwargs = mock_top_up.call_args.kwargs
    assert call_kwargs["amount"] == 1000.0
    assert "virtual_lab_id" in call_kwargs


@pytest.mark.asyncio
async def test_provision_seats_institution_from_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
    institution_id: str,
) -> None:
    """Seats should get institution_id from the course, not the request."""
    body = _provision_payload(course_for_seats, number_of_seats=1)

    with patch(
        "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
    ) as mock_top_up:
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    seat = response.json()["data"]["seats"][0]
    assert seat["institution_id"] == institution_id


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provision_seats_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    body = _provision_payload(str(uuid4()))

    response = await async_test_client.post(
        "/seats/provision",
        json=body,
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_provision_seats_fails_for_non_admin(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = _provision_payload(str(uuid4()))

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=headers
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_provision_seats_fails_for_draft_course(
    async_test_client: AsyncClient,
    draft_course_for_seats: str,
) -> None:
    """Cannot provision seats for a course that is still in DRAFT status."""
    body = _provision_payload(draft_course_for_seats, number_of_seats=2)

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 409
    assert "draft" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_provision_seats_fails_for_voided_course(
    async_test_client: AsyncClient,
    voided_course_for_seats: str,
) -> None:
    """Cannot provision seats for a course that has been voided."""
    body = _provision_payload(voided_course_for_seats, number_of_seats=2)

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 409
    assert "voided" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_provision_seats_fails_with_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    body = _provision_payload(str(uuid4()))

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_provision_seats_fails_when_accounting_fails(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    body = _provision_payload(course_for_seats, number_of_seats=1)

    with (
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
        patch(
            "virtual_labs.usecases.seat.provision_seats.settings.ACCOUNTING_BASE_URL",
            "http://accounting:8000",
        ),
    ):
        mock_top_up.side_effect = Exception("accounting service down")
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_provision_seats_fails_when_exceeding_max_batch_size(
    async_test_client: AsyncClient,
) -> None:
    body = _provision_payload(str(uuid4()), number_of_seats=101)

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_provision_seats_fails_with_zero_seats(
    async_test_client: AsyncClient,
) -> None:
    body = _provision_payload(str(uuid4()), number_of_seats=0)

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_provision_seats_fails_with_negative_seats(
    async_test_client: AsyncClient,
) -> None:
    body = _provision_payload(str(uuid4()), number_of_seats=-1)

    response = await async_test_client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_provision_seats_expiry_date_is_one_year(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Seats should have an expiry date approximately 1 year from now."""
    from datetime import datetime, timedelta, timezone

    body = _provision_payload(course_for_seats, number_of_seats=1)

    with patch(
        "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
    ) as mock_top_up:
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    seat = response.json()["data"]["seats"][0]
    expiry = datetime.fromisoformat(seat["expiry_date"])
    expected = datetime.now(timezone.utc) + timedelta(days=365)
    # Allow 60 seconds tolerance for test execution time
    assert abs((expiry - expected).total_seconds()) < 60
