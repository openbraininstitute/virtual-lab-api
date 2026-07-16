from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from virtual_labs.infrastructure.db.models import Course, Seat, VirtualLab
from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.seats.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.utils import (
    cleanup_course,
    cleanup_resources,
    get_headers,
    session_context_factory,
)


async def _create_active_course(
    async_test_client: AsyncClient,
    institution_id: str,
) -> tuple[str, str]:
    client = async_test_client
    headers = get_headers()

    lab_body = {
        "name": f"Transfer Lab {uuid4()}",
        "description": "Test transfer lab",
        "reference_email": "transfer@test.org",
        "entity": "EPFL, Switzerland",
        "is_course": True,
    }
    lab_response = await client.post("/virtual-labs", json=lab_body, headers=headers)
    assert lab_response.status_code == 200
    lab_id = lab_response.json()["id"]

    async with session_context_factory() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    project_body = {
        "name": f"Template Project {uuid4()}",
        "description": "Template",
    }
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    course_body = {
        "virtual_lab_id": lab_id,
        "template_project_id": project_id,
        "institution_id": institution_id,
    }
    course_response = await client.post(
        "/courses", json=course_body, headers=SERVICE_ADMIN_HEADERS
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["data"]["id"]

    await client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2026-09-01T00:00:00Z",
            "end_date": "2026-12-15T00:00:00Z",
            "last_drop_date": "2026-09-14T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )
    activate_response = await client.post(
        f"/courses/{course_id}/activate", headers=SERVICE_ADMIN_HEADERS
    )
    assert activate_response.status_code == 200

    return course_id, lab_id


@pytest.mark.asyncio
async def test_transfer_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
    institution_id: str,
) -> None:
    source_course_id = course_for_seats
    target_course_id, lab_id = await _create_active_course(
        async_test_client, institution_id
    )

    try:
        async with session_context_factory() as session:
            source_course = await session.get(Course, UUID(source_course_id))
            target_course = await session.get(Course, UUID(target_course_id))
            assert source_course is not None
            assert target_course is not None
            source_course.last_drop_date = datetime.now(timezone.utc) - timedelta(
                days=1
            )
            target_course.last_drop_date = datetime.now(timezone.utc) + timedelta(
                days=5
            )
            await session.commit()

        provision_response = await async_test_client.post(
            "/seats/provision",
            json={"course_id": source_course_id, "number_of_seats": 2},
            headers=SERVICE_ADMIN_HEADERS,
        )
        assert provision_response.status_code == 200

        transfer_response = await async_test_client.post(
            "/seats/transfer",
            json={
                "source_course_id": source_course_id,
                "target_course_id": target_course_id,
                "amount": "all",
            },
            headers=SERVICE_ADMIN_HEADERS,
        )

        assert transfer_response.status_code == 200
        payload = transfer_response.json()["data"]
        assert payload["transferred_count"] == 2
        assert len(payload["transferred_seats"]) == 2
        assert all(
            seat["course_id"] == target_course_id
            for seat in payload["transferred_seats"]
        )

        async with session_context_factory() as session:
            result = await session.execute(
                select(Seat).where(Seat.course_id == UUID(target_course_id))
            )
            transferred_seats = result.scalars().all()
            assert len(transferred_seats) == 2
    finally:
        async with session_context_factory() as session:
            await session.execute(
                update(Seat)
                .where(Seat.course_id == UUID(target_course_id))
                .values(course_id=UUID(source_course_id))
            )
            await session.commit()
        await cleanup_course(target_course_id)
        await cleanup_resources(async_test_client, lab_id)
