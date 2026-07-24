"""Tests for POST /courses/{course_id}/enrolment/activate."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, CourseStatus
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_assign_seats import mock_assign_accounting
from virtual_labs.tests.utils import get_headers, session_context_factory

_KC_PATCH = "virtual_labs.usecases.course.activate_enrolment._activate_in_kc"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _assign_and_claim(
    client: AsyncClient,
    course_id: str,
    *,
    claim_user: str = "test",
) -> str:
    """Provision a seat, assign it, claim it, and return the enrolment_id."""
    await provision_seats(client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }

    with mock_assign_accounting():
        assign_resp = await client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=get_headers(),
        )
    assert assign_resp.status_code == 200
    enrolment_id = assign_resp.json()["results"][0]["enrolment_id"]

    claim_resp = await client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=get_headers(claim_user),
    )
    assert claim_resp.status_code == 200

    return enrolment_id


def _url(course_id: str) -> str:
    return f"/courses/{course_id}/enrolment/activate"


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_enrolment_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Activating a claimed enrolment returns activated=True and project_id."""
    enrolment_id = await _assign_and_claim(async_test_client, course_for_seats)

    with patch(_KC_PATCH, new_callable=AsyncMock) as mock_kc:
        response = await async_test_client.post(
            _url(course_for_seats), headers=get_headers()
        )

    assert response.status_code == 200
    data = response.json()
    assert data["enrolment_id"] == enrolment_id
    assert data["activated"] is True
    assert data["project_id"] is not None
    assert data["error"] is None
    mock_kc.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_enrolment_idempotent(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Calling activate twice returns 200 both times — KC not called on second."""
    await _assign_and_claim(async_test_client, course_for_seats)

    with patch(_KC_PATCH, new_callable=AsyncMock):
        resp1 = await async_test_client.post(
            _url(course_for_seats), headers=get_headers()
        )
    assert resp1.status_code == 200
    assert resp1.json()["activated"] is True

    with patch(_KC_PATCH, new_callable=AsyncMock) as mock_kc:
        resp2 = await async_test_client.post(
            _url(course_for_seats), headers=get_headers()
        )
    assert resp2.status_code == 200
    assert resp2.json()["activated"] is True
    mock_kc.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_enrolment_no_enrolment(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns 404 when the user has no enrolment in the course."""
    response = await async_test_client.post(
        _url(course_for_seats), headers=get_headers()
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_activate_enrolment_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    """Returns 404 for a nonexistent course."""
    response = await async_test_client.post(_url(str(uuid4())), headers=get_headers())
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_activate_enrolment_dropped(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns 409 for a dropped enrolment."""
    enrolment_id = await _assign_and_claim(async_test_client, course_for_seats)

    async with session_context_factory() as session:
        await session.execute(
            update(CourseEnrolment)
            .where(CourseEnrolment.id == UUID(enrolment_id))
            .values(is_dropped=True)
        )
        await session.commit()

    response = await async_test_client.post(
        _url(course_for_seats), headers=get_headers()
    )
    assert response.status_code == 409
    assert "dropped" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_activate_enrolment_ended_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns 409 when the course has already ended."""
    await _assign_and_claim(async_test_client, course_for_seats)

    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_for_seats))
            .values(end_date=datetime(2020, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    response = await async_test_client.post(
        _url(course_for_seats), headers=get_headers()
    )
    assert response.status_code == 409
    assert "ended" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_activate_enrolment_not_started_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns 409 when the course has not started yet."""
    await _assign_and_claim(async_test_client, course_for_seats)

    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_for_seats))
            .values(start_date=datetime(2099, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    response = await async_test_client.post(
        _url(course_for_seats), headers=get_headers()
    )
    assert response.status_code == 409
    assert "not started" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_activate_enrolment_voided_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns 409 when the course is voided."""
    await _assign_and_claim(async_test_client, course_for_seats)

    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_for_seats))
            .values(status=CourseStatus.VOIDED)
        )
        await session.commit()

    response = await async_test_client.post(
        _url(course_for_seats), headers=get_headers()
    )
    assert response.status_code == 409
    assert "voided" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_activate_enrolment_kc_failure_raises(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If KC group add fails, the endpoint returns 500 (ledger compensates)."""
    await _assign_and_claim(async_test_client, course_for_seats)

    with patch(
        _KC_PATCH,
        new_callable=AsyncMock,
        side_effect=Exception("KC unavailable"),
    ):
        response = await async_test_client.post(
            _url(course_for_seats), headers=get_headers()
        )

    assert response.status_code == 500


# ──────────────────────────────────────────────────────────────────────
# Auth tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_enrolment_unauthenticated(
    async_test_client: AsyncClient,
) -> None:
    """Request without auth is rejected."""
    response = await async_test_client.post(
        _url(str(uuid4())),
        headers={"Content-Type": "application/json", "Authorization": ""},
    )
    assert response.status_code == 401
