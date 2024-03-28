from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from requests import get

from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.tests.utils import get_headers


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "budget": 10,
        "plan_id": 1,
    }
    headers = get_headers()
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    yield response, headers

    lab_id = response.json()["data"]["virtual_lab"]["id"]
    response = await client.delete(f"/virtual-labs/{lab_id}", headers=get_headers())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_virtual_lab_created(
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    response, headers = mock_lab_create
    # Test that the virtual lab was created
    assert response.status_code == 200
    lab_id = response.json()["data"]["virtual_lab"]["id"]

    group_repo = GroupQueryRepository()
    group_id = f"vlab/{lab_id}/admin"

    # Test that the keycloak admin group was created
    group = group_repo.retrieve_group_by_name(name=group_id)
    assert group is not None

    nexus_org_request = get(
        f"{settings.NEXUS_DELTA_URI}/orgs/{str(lab_id)}", headers=headers
    )
    # Test that the nexus organization was created
    assert nexus_org_request.status_code == 200
