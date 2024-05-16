from uuid import UUID

import pytest
from httpx import AsyncClient

from virtual_labs.core.exceptions.api_error import VliErrorCode
from virtual_labs.shared.utils.billing import amount_to_cent


@pytest.mark.asyncio
async def test_update_project_budget_operation_not_allowed(
    async_test_client: AsyncClient,
    mock_create_projects: tuple[UUID, float, list[UUID], dict[str, str]],
) -> None:
    client = async_test_client
    (vlab_id, vlab_budget, projects, headers) = mock_create_projects

    project_test_id = projects[0]
    new_budget = (vlab_budget / len(projects)) + 100

    response = await client.patch(
        f"/virtual-labs/{vlab_id}/projects/{project_test_id}/budget",
        json={"new_budget": new_budget},
        headers=headers,
    )
    details = response.json()

    assert response.status_code == 406
    assert details["error_code"] == VliErrorCode.NOT_ALLOWED_OP


@pytest.mark.asyncio
async def test_update_project_budget_success(
    async_test_client: AsyncClient,
    mock_create_projects: tuple[UUID, float, list[UUID], dict[str, str]],
) -> None:
    client = async_test_client
    (vlab_id, _, projects, headers) = mock_create_projects

    project_test_id = projects[0]
    new_budget = 100.96

    response = await client.patch(
        f"/virtual-labs/{vlab_id}/projects/{project_test_id}/budget",
        json={"new_budget": new_budget},
        headers=headers,
    )
    details = response.json()

    assert response.status_code == 200
    assert details["data"]["new_budget"] == amount_to_cent(new_budget)
