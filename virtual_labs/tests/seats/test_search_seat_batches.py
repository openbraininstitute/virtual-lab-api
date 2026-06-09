"""Tests for the seat batch search endpoints."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.utils import (
    get_headers,
    mock_admin_userinfo,
    mock_non_admin_userinfo,
)

# ──────────────────────────────────────────────────────────────────────
# GET /seats/batches/{batch_id}
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_seat_batch_by_id(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    data = await provision_seats(async_test_client, course_for_seats)
    batch_id = data["seats"][0]["batch_id"]

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            f"/seats/batches/{batch_id}", headers=headers
        )

    assert response.status_code == 200
    result = response.json()
    assert "institution" in result
    assert "course" in result
    assert "batches" in result
    assert len(result["batches"]) == 1
    batch = result["batches"][0]
    assert batch["batch_id"] == batch_id
    assert batch["number_of_seats"] == 2
    assert len(batch["seats"]) == 2


@pytest.mark.asyncio
async def test_get_seat_batch_includes_course_details(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    data = await provision_seats(async_test_client, course_for_seats)
    batch_id = data["seats"][0]["batch_id"]

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            f"/seats/batches/{batch_id}", headers=headers
        )

    assert response.status_code == 200
    result = response.json()
    course = result["course"]
    assert "virtual_lab_name" in course
    assert "virtual_lab_id" in course
    assert "status" in course


@pytest.mark.asyncio
async def test_get_seat_batch_includes_institution_details(
    async_test_client: AsyncClient,
    course_for_seats: str,
    institution_id: str,
) -> None:
    data = await provision_seats(async_test_client, course_for_seats)
    batch_id = data["seats"][0]["batch_id"]

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            f"/seats/batches/{batch_id}", headers=headers
        )

    assert response.status_code == 200
    result = response.json()
    institution = result["institution"]
    assert institution["id"] == institution_id
    assert "name" in institution
    assert "contact_email" in institution


@pytest.mark.asyncio
async def test_get_seat_batch_not_found(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            f"/seats/batches/{uuid4()}", headers=headers
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_seat_batch_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.get(
        f"/seats/batches/{uuid4()}",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )
    assert response.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# GET /seats/batches?filters
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_seat_batches_by_course_id(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    await provision_seats(async_test_client, course_for_seats, number_of_seats=3)
    await provision_seats(async_test_client, course_for_seats, number_of_seats=2)

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            "/seats/batches", params={"course_id": course_for_seats}, headers=headers
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result["batches"]) == 2
    # Verify batch sizes
    sizes = sorted(b["number_of_seats"] for b in result["batches"])
    assert sizes == [2, 3]


@pytest.mark.asyncio
async def test_search_seat_batches_by_institution_id(
    async_test_client: AsyncClient,
    course_for_seats: str,
    institution_id: str,
) -> None:
    await provision_seats(async_test_client, course_for_seats)

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            "/seats/batches",
            params={"institution_id": institution_id},
            headers=headers,
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result["batches"]) >= 1
    assert result["institution"]["id"] == institution_id


@pytest.mark.asyncio
async def test_search_seat_batches_by_vlab_name(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    await provision_seats(async_test_client, course_for_seats)

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Use "Course Lab" which is part of the lab name created by fixtures
        response = await async_test_client.get(
            "/seats/batches", params={"vlab_name": "Course Lab"}, headers=headers
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result["batches"]) >= 1


@pytest.mark.asyncio
async def test_search_seat_batches_by_institution_name(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    await provision_seats(async_test_client, course_for_seats)

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            "/seats/batches",
            params={"institution_name": "Open Brain"},
            headers=headers,
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result["batches"]) >= 1


@pytest.mark.asyncio
async def test_search_seat_batches_no_results(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.get(
            "/seats/batches", params={"course_id": str(uuid4())}, headers=headers
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_seat_batches_fails_for_non_admin(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_non_admin_userinfo
        response = await async_test_client.get(
            "/seats/batches", params={"course_id": str(uuid4())}, headers=headers
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_seat_batches_by_created_after(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    await provision_seats(async_test_client, course_for_seats)

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Use a date in the past to ensure we find the batch
        response = await async_test_client.get(
            "/seats/batches",
            params={
                "course_id": course_for_seats,
                "created_after": "2020-01-01T00:00:00Z",
            },
            headers=headers,
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result["batches"]) >= 1


@pytest.mark.asyncio
async def test_search_seat_batches_by_created_before_filters_out(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    await provision_seats(async_test_client, course_for_seats)

    headers = get_headers()
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Use a date in the past to ensure nothing is found
        response = await async_test_client.get(
            "/seats/batches",
            params={
                "course_id": course_for_seats,
                "created_before": "2020-01-01T00:00:00Z",
            },
            headers=headers,
        )

    assert response.status_code == 404
