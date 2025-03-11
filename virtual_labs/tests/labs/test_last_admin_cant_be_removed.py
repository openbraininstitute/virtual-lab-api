from http import HTTPStatus
from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.infrastructure.kc.models import UserRepresentation
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.tests.utils import cleanup_resources, create_mock_lab


@pytest_asyncio.fixture
async def mock_lab(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str], None]:
    lab_response = await create_mock_lab(async_test_client)
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    yield async_test_client, lab_id

    await cleanup_resources(client=async_test_client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_last_admin_cannot_be_deleted(
    mock_lab: tuple[AsyncClient, str],
) -> None:
    client, lab_id = mock_lab
    admin_id = (
        cast(
            UserRepresentation,
            UserQueryRepository().retrieve_user_by_email("test@test.com"),
        )
    ).id
    delete_admin_response = await client.delete(
        f"/virtual-labs/{lab_id}/users/{admin_id}"
    )
    assert delete_admin_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (
        delete_admin_response.json()["message"]
        == f"Last admin of lab {lab_id} cannot be removed"
    )


@pytest.mark.asyncio
async def test_last_admin_cannot_be_converted_to_member(
    mock_lab: tuple[AsyncClient, str],
) -> None:
    client, lab_id = mock_lab
    admin_id = (
        cast(
            UserRepresentation,
            UserQueryRepository().retrieve_user_by_email("test@test.com"),
        )
    ).id
    change_role_response = await client.patch(
        f"/virtual-labs/{lab_id}/users/{admin_id}?new_role=member"
    )
    assert change_role_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (
        change_role_response.json()["message"]
        == f"Last admin of lab {lab_id} cannot be converted to member"
    )
