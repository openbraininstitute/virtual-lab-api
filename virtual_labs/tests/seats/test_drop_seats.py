"""Tests for the drop-seats endpoint (POST /courses/{course_id}/drop_seats)."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, Project
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_assign_seats import mock_enrolment_email
from virtual_labs.tests.utils import get_headers, session_context_factory


def _drop_payload(seat_ids: list[str] | None = None) -> dict:
    if seat_ids is None:
        seat_ids = [str(uuid4())]
    return {"seat_ids": seat_ids}


# ──────────────────────────────────────────────────────────────────────
# Authorization tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_fails_for_non_admin_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A user who is not a vlab admin cannot drop seats."""
    headers = get_headers("test-1")  # different user, not admin of this lab
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_drop_seats_fails_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    """Returns 403 for a nonexistent course (verify_course_admin fails)."""
    headers = get_headers()
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{uuid4()}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_drop_seats_fails_without_auth(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# Validation tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_rejects_empty_seat_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Empty seat_ids list is rejected by validation."""
    headers = get_headers()
    body = {"seat_ids": []}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_drop_seats_rejects_duplicate_seat_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Duplicate seat_id in request is rejected by validation."""
    headers = get_headers()
    seat_id = str(uuid4())
    body = {"seat_ids": [seat_id, seat_id]}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Non-existent seat test
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_nonexistent_seat_returns_error_in_results(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping a seat that doesn't exist returns drop_successful=False in results."""
    headers = get_headers()
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert "not found" in results[0]["error"].lower()


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Provision seats, assign one, then drop it successfully (pre-activation)."""

    headers = get_headers()
    course_id = course_for_seats

    # Provision 2 seats
    await provision_seats(async_test_client, course_id, 2)

    # Assign one seat
    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_enrolment_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]
    assert seat_id is not None

    # Drop the seat (pre-activation: no project, no accounting needed)
    drop_resp = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["seat_id"] == seat_id
    assert results[0]["drop_successful"] is True
    assert results[0]["error"] is None


@pytest.mark.asyncio
async def test_drop_seats_post_activation(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Drop a seat after activation: KC groups cleared and budget reversed."""
    headers = get_headers()
    course_id = course_for_seats

    # Provision and assign
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_enrolment_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]
    enrolment_id = assign_resp.json()["results"][0]["enrolment_id"]

    # Simulate activation: create a fake project and set enrolment.project_id
    async with session_context_factory() as session:
        project = Project(
            id=uuid4(),
            admin_group_id=f"admin-{uuid4().hex[:8]}",
            member_group_id=f"member-{uuid4().hex[:8]}",
            owner_id=uuid4(),
            name=f"test-project-{uuid4().hex[:8]}",
            virtual_lab_id=UUID(course_id),  # not accurate but FK not enforced in test
        )
        # We need the real vlab_id — get it from the enrolment's course
        course_obj = await session.get(Course, UUID(course_id))
        assert course_obj is not None
        project.virtual_lab_id = course_obj.virtual_lab_id
        session.add(project)
        await session.flush()

        enrolment = await session.get(CourseEnrolment, UUID(enrolment_id))
        assert enrolment is not None
        enrolment.project_id = project.id
        await session.commit()

    # Drop the seat (post-activation: mock KC and accounting)
    with (
        patch(
            "virtual_labs.usecases.course.drop_seats._clear_project_groups",
            new_callable=AsyncMock,
        ) as mock_clear_groups,
        patch(
            "virtual_labs.usecases.course.drop_seats._reverse_project_budget",
            new_callable=AsyncMock,
        ) as mock_reverse_budget,
    ):
        drop_resp = await async_test_client.post(
            f"/courses/{course_id}/drop_seats",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["seat_id"] == seat_id
    assert results[0]["drop_successful"] is True
    assert results[0]["error"] is None

    # Verify KC and accounting were called
    mock_clear_groups.assert_awaited_once()
    mock_reverse_budget.assert_awaited_once()


@pytest.mark.asyncio
async def test_drop_seats_post_activation_kc_failure(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Post-activation drop fails gracefully when KC group cleanup fails."""
    headers = get_headers()
    course_id = course_for_seats

    # Provision and assign
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_enrolment_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]
    enrolment_id = assign_resp.json()["results"][0]["enrolment_id"]

    # Simulate activation with a project that has bogus KC group IDs
    async with session_context_factory() as session:
        course_obj = await session.get(Course, UUID(course_id))
        assert course_obj is not None

        project = Project(
            id=uuid4(),
            admin_group_id=f"bogus-admin-{uuid4().hex[:8]}",
            member_group_id=f"bogus-member-{uuid4().hex[:8]}",
            owner_id=uuid4(),
            name=f"test-project-{uuid4().hex[:8]}",
            virtual_lab_id=course_obj.virtual_lab_id,
        )
        session.add(project)
        await session.flush()

        enrolment = await session.get(CourseEnrolment, UUID(enrolment_id))
        assert enrolment is not None
        enrolment.project_id = project.id
        await session.commit()

    # Drop WITHOUT mocking KC — the bogus group IDs will cause a real failure
    drop_resp = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["seat_id"] == seat_id
    assert results[0]["drop_successful"] is False
    assert results[0]["error"] is not None


# ──────────────────────────────────────────────────────────────────────
# Multi-seat and edge-case tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_unassigned_seat(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping a provisioned but unassigned seat returns 'no enrolment'."""
    headers = get_headers()
    course_id = course_for_seats

    # Provision without assigning
    prov = await provision_seats(async_test_client, course_id, 1)
    seat_id = prov["seats"][0]["id"]

    drop_resp = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert "no enrolment" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_drop_seats_already_dropped(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping a seat that was already dropped (early): seat is recycled, shows 'no enrolment'."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_enrolment_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    # Drop it once (early drop — seat is recycled, enrolment_id set to None)
    drop_resp = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )
    assert drop_resp.status_code == 200
    assert drop_resp.json()["results"][0]["drop_successful"] is True

    # Drop it again — seat now has no enrolment (recycled)
    drop_resp2 = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )
    assert drop_resp2.status_code == 200
    results = drop_resp2.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert "no enrolment" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_drop_multiple_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping multiple valid seats in one call succeeds for all."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 3)

    students = [
        {
            "student_id": f"stu-{uuid4().hex[:8]}",
            "email": f"{uuid4().hex[:8]}@uni.org",
        }
        for _ in range(3)
    ]
    with mock_enrolment_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": students},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_ids = [r["seat_id"] for r in assign_resp.json()["results"]]
    assert len(seat_ids) == 3

    # Drop all 3 at once
    drop_resp = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": seat_ids},
        headers=headers,
    )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 3
    for r in results:
        assert r["drop_successful"] is True
        assert r["error"] is None


@pytest.mark.asyncio
async def test_drop_seats_mixed_valid_and_invalid(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Mix of valid, unassigned, and nonexistent seats — each gets correct result."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 2)

    # Assign only 1 of the 2
    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_enrolment_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    assigned_seat_id = assign_resp.json()["results"][0]["seat_id"]

    # Get the unassigned seat
    list_resp = await async_test_client.get(
        f"/seats/courses/{course_id}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    all_seats = list_resp.json()["seats"]
    unassigned_seat_id = next(s["id"] for s in all_seats if s["enrolment_id"] is None)

    nonexistent_seat_id = str(uuid4())

    # Drop all 3 in one call
    drop_resp = await async_test_client.post(
        f"/courses/{course_id}/drop_seats",
        json={"seat_ids": [assigned_seat_id, unassigned_seat_id, nonexistent_seat_id]},
        headers=headers,
    )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 3

    result_map = {r["seat_id"]: r for r in results}

    # Assigned seat: dropped successfully
    assert result_map[assigned_seat_id]["drop_successful"] is True

    # Unassigned seat: no enrolment
    assert result_map[unassigned_seat_id]["drop_successful"] is False
    assert "no enrolment" in result_map[unassigned_seat_id]["error"].lower()

    # Nonexistent seat: not found
    assert result_map[nonexistent_seat_id]["drop_successful"] is False
    assert "not found" in result_map[nonexistent_seat_id]["error"].lower()
