"""Shared test helpers for seat tests."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers, mock_admin_userinfo


async def provision_seats(
    client: AsyncClient, course_id: str, number_of_seats: int = 2
) -> dict:
    """Provision seats for a course and return the response data."""
    headers = get_headers()
    body = {"course_id": course_id, "number_of_seats": number_of_seats}

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
        response = await client.post("/seats/provision", json=body, headers=headers)

    assert response.status_code == 200
    return response.json()["data"]
