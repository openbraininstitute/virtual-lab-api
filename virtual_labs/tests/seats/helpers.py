"""Shared test helpers for seat tests."""

from httpx import AsyncClient

from virtual_labs.tests.seats.conftest import SERVICE_ADMIN_HEADERS


async def provision_seats(
    client: AsyncClient, course_id: str, number_of_seats: int = 2
) -> dict:
    """Provision seats for a course and return the response data."""
    body = {"course_id": course_id, "number_of_seats": number_of_seats}

    response = await client.post(
        "/seats/provision", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 200
    return response.json()["data"]
