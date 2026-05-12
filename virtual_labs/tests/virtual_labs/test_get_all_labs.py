"""Integration tests for the user-vlab listing endpoints.

The single legacy `GET /virtual-labs` use case has been split into:

  * ``GET /virtual-labs/me`` — the requester's owned lab.
  * ``GET /virtual-labs`` — paginated tenant list with ``scope`` and
    ``admin_access_only`` filters plus ``order_by`` / ``order_direction``.
  * ``GET /virtual-labs/awaiting`` — paginated pending invitations
    (not exercised here — covered by the invite tests).
"""

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


@pytest_asyncio.fixture
async def multiple_mock_labs(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, list[tuple[Any, str]]], None]:
    """Three labs owned by three different users; each user is admin
    of exactly one lab via the standard create flow."""
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

    for lab, user in all_labs:
        await cleanup_resources(client=async_test_client, lab_id=lab["id"], user=user)


@pytest.mark.asyncio
async def test_get_my_virtual_lab(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    """`GET /virtual-labs/me` returns the requester's owned lab."""
    client, labs_with_users = multiple_mock_labs

    for expected_lab, owner_user in labs_with_users:
        response = await client.get("/virtual-labs/me", headers=get_headers(owner_user))
        assert response.status_code == 200

        body = response.json()["data"]
        assert body is not None, f"expected owned lab for {owner_user}"
        assert body["id"] == expected_lab["id"]


@pytest.mark.asyncio
async def test_list_tenant_virtual_labs_default(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    """Default scope (``all``) surfaces the requester's owned lab.

    The endpoint is robust even when the realm doesn't expose the
    ``groups`` claim via ``/userinfo`` — DB ownership is folded into
    the candidate set so the owner always sees their own lab.
    """
    client, labs_with_users = multiple_mock_labs

    for expected_lab, owner_user in labs_with_users:
        response = await client.get("/virtual-labs", headers=get_headers(owner_user))
        assert response.status_code == 200

        payload = response.json()["data"]
        assert "data" in payload and "pagination" in payload
        ids = {item["id"] for item in payload["data"]}
        assert expected_lab["id"] in ids


@pytest.mark.asyncio
async def test_list_tenant_virtual_labs_scope_self(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    """``scope=self`` keeps only labs the requester owns."""
    client, labs_with_users = multiple_mock_labs

    for expected_lab, owner_user in labs_with_users:
        response = await client.get(
            "/virtual-labs?scope=self", headers=get_headers(owner_user)
        )
        assert response.status_code == 200

        payload = response.json()["data"]
        ids = {item["id"] for item in payload["data"]}
        assert expected_lab["id"] in ids
        # `scope=self` must never surface a lab owned by someone else.
        for item in payload["data"]:
            assert item["id"] == expected_lab["id"], (
                f"scope=self for {owner_user} leaked lab {item['id']} "
                f"(owned by another user)"
            )


@pytest.mark.asyncio
async def test_list_tenant_virtual_labs_scope_external(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    """``scope=external`` excludes the requester's owned lab."""
    client, labs_with_users = multiple_mock_labs

    for expected_lab, owner_user in labs_with_users:
        response = await client.get(
            "/virtual-labs?scope=external", headers=get_headers(owner_user)
        )
        assert response.status_code == 200

        payload = response.json()["data"]
        ids = {item["id"] for item in payload["data"]}
        assert expected_lab["id"] not in ids


@pytest.mark.asyncio
async def test_list_tenant_pagination_envelope(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    """The shared `PaginatedResponse` envelope is well-formed."""
    client, labs_with_users = multiple_mock_labs
    _, owner_user = labs_with_users[0]

    response = await client.get(
        "/virtual-labs?page=1&size=10", headers=get_headers(owner_user)
    )
    assert response.status_code == 200

    payload = response.json()["data"]
    pagination = payload["pagination"]
    assert pagination["page"] == 1
    assert pagination["size"] == 10
    assert pagination["page_size"] == len(payload["data"])
    assert pagination["total"] >= pagination["page_size"]
    assert pagination["has_previous"] is False


@pytest.mark.asyncio
async def test_list_tenant_invalid_scope(
    multiple_mock_labs: tuple[AsyncClient, list[tuple[Any, str]]],
) -> None:
    """Bad enum values for ``scope`` yield 422 (handled by FastAPI)."""
    client, labs_with_users = multiple_mock_labs
    _, owner_user = labs_with_users[0]

    response = await client.get(
        "/virtual-labs?scope=bogus", headers=get_headers(owner_user)
    )
    assert response.status_code == 422
