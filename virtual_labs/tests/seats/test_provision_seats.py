"""Tests for the provision-seats endpoint (POST /seats/provision)."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import (
    get_headers,
    mock_admin_userinfo,
    mock_non_admin_userinfo,
)


def _provision_payload(virtual_lab_id: str, number_of_seats: int = 3) -> dict:
    return {
        "virtual_lab_id": virtual_lab_id,
        "number_of_seats": number_of_seats,
    }


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provision_seats_success(
    async_test_client: AsyncClient,
    vlab_with_course: str,
) -> None:
    headers = get_headers()
    body = _provision_payload(vlab_with_course, number_of_seats=2)

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
    ):
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["seats"]) == 2
    assert data["total_credits_topped_up"] == 400.0
    batch_ids = set()
    for seat in data["seats"]:
        assert seat["virtual_lab_id"] == vlab_with_course
        assert seat["is_consumed"] is False
        assert seat["active_project_id"] is None
        assert "batch_id" in seat
        batch_ids.add(seat["batch_id"])
    # All seats in the same provision call share one batch_id
    assert len(batch_ids) == 1


@pytest.mark.asyncio
async def test_provision_seats_calls_accounting_top_up(
    async_test_client: AsyncClient,
    vlab_with_course: str,
) -> None:
    headers = get_headers()
    body = _provision_payload(vlab_with_course, number_of_seats=5)

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
        patch(
            "virtual_labs.usecases.seat.provision_seats.settings.ACCOUNTING_BASE_URL",
            "http://accounting:8000",
        ),
    ):
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 200
    mock_top_up.assert_awaited_once_with(
        virtual_lab_id=UUID(body["virtual_lab_id"]),
        amount=1000.0,
    )


@pytest.mark.asyncio
async def test_provision_seats_institution_from_course(
    async_test_client: AsyncClient,
    vlab_with_course: str,
    institution_id: str,
) -> None:
    """Seats should get institution_id from the course, not the request."""
    headers = get_headers()
    body = _provision_payload(vlab_with_course, number_of_seats=1)

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
    ):
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
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

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_non_admin_userinfo
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_provision_seats_fails_with_nonexistent_vlab(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = _provision_payload(str(uuid4()))

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_provision_seats_fails_without_course(
    async_test_client: AsyncClient,
    vlab_without_course: str,
) -> None:
    headers = get_headers()
    body = _provision_payload(vlab_without_course)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_provision_seats_fails_when_accounting_fails(
    async_test_client: AsyncClient,
    vlab_with_course: str,
) -> None:
    headers = get_headers()
    body = _provision_payload(vlab_with_course, number_of_seats=1)

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
        patch(
            "virtual_labs.usecases.seat.provision_seats.settings.ACCOUNTING_BASE_URL",
            "http://accounting:8000",
        ),
    ):
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        mock_top_up.side_effect = Exception("accounting service down")
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_provision_seats_fails_with_zero_seats(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = _provision_payload(str(uuid4()), number_of_seats=0)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_provision_seats_fails_with_negative_seats(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = _provision_payload(str(uuid4()), number_of_seats=-1)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_provision_seats_expiry_date_is_one_year(
    async_test_client: AsyncClient,
    vlab_with_course: str,
) -> None:
    """Seats should have an expiry date approximately 1 year from now."""
    from datetime import datetime, timedelta, timezone

    headers = get_headers()
    body = _provision_payload(vlab_with_course, number_of_seats=1)

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
        ) as mock_top_up,
    ):
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        mock_top_up.return_value = AsyncMock()
        response = await async_test_client.post(
            "/seats/provision", json=body, headers=headers
        )

    assert response.status_code == 200
    seat = response.json()["data"]["seats"][0]
    expiry = datetime.fromisoformat(seat["expiry_date"])
    expected = datetime.now(timezone.utc) + timedelta(days=365)
    # Allow 60 seconds tolerance for test execution time
    assert abs((expiry - expected).total_seconds()) < 60
