"""Shared test helpers for seat tests."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from virtual_labs.tests.seats.conftest import SERVICE_ADMIN_HEADERS


async def provision_seats(
    client: AsyncClient, course_id: str, number_of_seats: int = 2
) -> dict:
    """Provision seats for a course and return the response data."""
    body = {"course_id": course_id, "number_of_seats": number_of_seats}

    with patch(
        "virtual_labs.usecases.seat.provision_seats.accounting_cases.top_up_virtual_lab_budget"
    ) as mock_top_up:
        mock_top_up.return_value = AsyncMock()
        response = await client.post(
            "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    return response.json()["data"]
