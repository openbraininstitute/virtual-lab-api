from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
    create_mock_lab_with_project,
    get_headers,
)


async def delete_lab(client: AsyncClient, lab_id: str) -> None:
    headers_for_test_user = get_headers()
    response = await client.delete(
        f"/virtual-labs/{lab_id}", headers=headers_for_test_user
    )
    assert response.status_code == 200


@pytest_asyncio.fixture
async def multiple_mock_labs(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, list[tuple[Any, str]]], None]:
    lab1 = await create_mock_lab(async_test_client, "test")
    lab2_data, _project_id = await create_mock_lab_with_project(
        async_test_client, "test-1"
    )
    lab3 = await create_mock_lab(async_test_client, "test-2")

    all_labs = [
        (lab1.json()["data"]["virtual_lab"], "test"),
        (lab2_data, "test-1"),
        (lab3.json()["data"]["virtual_lab"], "test-2"),
    ]
    yield async_test_client, all_labs

    await cleanup_resources(
        client=async_test_client, lab_id=all_labs[0][0]["id"], user="test"
    )
    await cleanup_resources(
        client=async_test_client, lab_id=all_labs[1][0]["id"], user="test-1"
    )
    await cleanup_resources(
        client=async_test_client, lab_id=all_labs[2][0]["id"], user="test-2"
    )


@pytest.mark.asyncio
async def test_paginated_labs(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    client, labs_with_users = multiple_mock_labs

    for expected_lab, owner_user in labs_with_users:
        response = await client.get("/virtual-labs", headers=get_headers(owner_user))

        assert response.status_code == 200

        response_data = response.json()["data"]

        assert response_data["virtual_lab"] is not None
        assert response_data["virtual_lab"]["id"] == expected_lab["id"]
