from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, str, dict[str, str]], None]:
    client = async_test_client
    headers = get_headers()

    lab_response = await client.post(
        "/virtual-labs",
        json={
            "name": f"Test Lab {uuid4()}",
            "description": "Test",
            "reference_email": "user@test.org",
            "entity": "EPFL, Switzerland",
        },
        headers=headers,
    )

    if lab_response.status_code != 200:
        pytest.fail(
            f"Lab creation failed with status {lab_response.status_code}: {lab_response.text}"
        )

    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects",
        json={
            "name": f"Test Project {uuid4()}",
            "description": "Test",
            "contact_email": "existing@test.org",
        },
        headers=headers,
    )
    assert project_response.status_code == 200

    yield lab_id, project_response.json()["data"]["project"]["id"], headers

    try:
        await cleanup_resources(client=client, lab_id=lab_id)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_missing_emails_returns_unassigned(
    async_test_client: AsyncClient,
    mock_lab_with_project: tuple[str, str, dict[str, str]],
) -> None:
    lab_id, _, headers = mock_lab_with_project
    response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/missing-student-emails",
        json={"emails": ["existing@test.org", "missing@test.org"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert sorted(response.json()) == ["missing@test.org"]


@pytest.mark.asyncio
async def test_missing_emails_all_exist(
    async_test_client: AsyncClient,
    mock_lab_with_project: tuple[str, str, dict[str, str]],
) -> None:
    lab_id, _, headers = mock_lab_with_project
    response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/missing-student-emails",
        json={"emails": ["existing@test.org"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_missing_emails_none_exist(
    async_test_client: AsyncClient,
    mock_lab_with_project: tuple[str, str, dict[str, str]],
) -> None:
    lab_id, _, headers = mock_lab_with_project
    response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/missing-student-emails",
        json={"emails": ["a@test.org", "b@test.org"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert sorted(response.json()) == ["a@test.org", "b@test.org"]
