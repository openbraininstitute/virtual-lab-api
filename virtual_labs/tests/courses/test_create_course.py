"""Tests for the create-course endpoint.

The endpoint assigns an existing virtual lab and project to a new course.
It does NOT provision KC groups, accounting, or create vlab/project records.
"""

from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.courses.conftest import (
    cleanup_course,
    mock_admin_userinfo,
    mock_non_admin_userinfo,
)
from virtual_labs.tests.utils import (
    create_mock_lab_with_project,
    get_headers,
)


def _make_course_payload(
    virtual_lab_id: str, template_project_id: str, institution_id: str
) -> dict:
    return {
        "virtual_lab_id": virtual_lab_id,
        "template_project_id": template_project_id,
        "institution_id": institution_id,
    }


@pytest_asyncio.fixture
async def mock_create_course(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    headers = get_headers()
    vlab_id, project_id = vlab_with_project

    body = _make_course_payload(vlab_id, project_id, institution_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    yield response, headers

    # Cleanup course row (vlab/project cleaned by vlab_with_project fixture)
    if response.status_code == 200:
        course_id = response.json().get("data", {}).get("id")
        if course_id:
            await cleanup_course(course_id)


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_course_created_successfully(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    data = response.json()["data"]
    assert "id" in data
    assert "virtual_lab_id" in data
    assert "institution_id" in data
    assert "template_project_id" in data
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_course_assigns_existing_vlab_and_project(
    mock_create_course: tuple[Response, dict[str, str]],
    vlab_with_project: tuple[str, str],
) -> None:
    """The course should reference the pre-existing vlab and project, not create new ones."""
    response, _ = mock_create_course
    vlab_id, project_id = vlab_with_project

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["virtual_lab_id"] == vlab_id
    assert data["template_project_id"] == project_id


@pytest.mark.asyncio
async def test_course_default_status_is_draft(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "draft"


@pytest.mark.asyncio
async def test_course_creation_with_optional_dates(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> None:
    headers = get_headers()
    vlab_id, project_id = vlab_with_project

    body = {
        **_make_course_payload(vlab_id, project_id, institution_id),
        "start_date": "2026-09-01",
        "end_date": "2026-12-15",
        "last_drop_date": "2026-10-01",
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["start_date"] == "2026-09-01"
    assert data["end_date"] == "2026-12-15"
    assert data["last_drop_date"] == "2026-10-01"

    await cleanup_course(data["id"])


# ──────────────────────────────────────────────────────────────────────
# Validation / error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_course_creation_fails_with_nonexistent_vlab(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = _make_course_payload(str(uuid4()), str(uuid4()), institution_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_course_creation_fails_with_nonexistent_project(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> None:
    headers = get_headers()
    vlab_id, _ = vlab_with_project
    body = _make_course_payload(vlab_id, str(uuid4()), institution_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_course_creation_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    body = _make_course_payload(str(uuid4()), str(uuid4()), str(uuid4()))

    response = await async_test_client.post(
        "/courses",
        json=body,
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_course_creation_fails_for_non_admin_user(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = _make_course_payload(str(uuid4()), str(uuid4()), str(uuid4()))

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_non_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_course_creation_fails_without_virtual_lab_id(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {"template_project_id": str(uuid4()), "institution_id": institution_id}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_course_creation_fails_without_template_project_id(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {"virtual_lab_id": str(uuid4()), "institution_id": institution_id}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_course_creation_fails_without_institution_id(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {"virtual_lab_id": str(uuid4()), "template_project_id": str(uuid4())}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_course_creation_fails_duplicate_vlab(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> None:
    """A virtual lab can only have one course (unique constraint)."""
    headers = get_headers()
    vlab_id, project_id = vlab_with_project
    body = _make_course_payload(vlab_id, project_id, institution_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo

        resp1 = await async_test_client.post("/courses", json=body, headers=headers)
        assert resp1.status_code == 200

        resp2 = await async_test_client.post("/courses", json=body, headers=headers)
        assert resp2.status_code == 409

    await cleanup_course(resp1.json()["data"]["id"])


@pytest.mark.asyncio
async def test_course_creation_fails_for_regular_vlab(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    """A course cannot be created on a regular (non-course) virtual lab."""
    from virtual_labs.tests.utils import cleanup_resources

    # Create a normal lab (not marked as course lab)
    lab_data, project_id = await create_mock_lab_with_project(async_test_client)
    lab_id = lab_data["id"]

    headers = get_headers()
    body = _make_course_payload(lab_id, project_id, institution_id)

    try:
        with patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc:
            mock_kc.userinfo.side_effect = mock_admin_userinfo
            response = await async_test_client.post(
                "/courses", json=body, headers=headers
            )

        assert response.status_code == 403
    finally:
        await cleanup_resources(async_test_client, lab_id)
