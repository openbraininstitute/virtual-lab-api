from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import get_headers


def _mock_admin_userinfo(*args, **kwargs):
    return {"groups": [VLAB_SERVICE_ADMIN_GROUP]}


def _mock_non_admin_userinfo(*args, **kwargs):
    return {"groups": ["/some-other-group"]}


async def _create_institution(
    client: AsyncClient, headers: dict, name: str | None = None
) -> dict:
    """Helper to create an institution and return its data."""
    body = {
        "name": name or f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await client.post("/institutions", json=body, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]


# --- GET /institutions/{institution_id} ---


@pytest.mark.asyncio
async def test_get_institution_by_id(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            f"/institutions/{institution['id']}",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == institution["id"]
    assert data["name"] == institution["name"]
    assert data["contact_email"] == institution["contact_email"]


@pytest.mark.asyncio
async def test_get_institution_by_id_not_found(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    fake_id = uuid4()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            f"/institutions/{fake_id}",
            headers=headers,
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_institution_by_id_invalid_uuid(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/institutions/not-a-valid-uuid",
            headers=headers,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_institution_by_id_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    fake_id = uuid4()

    response = await async_test_client.get(
        f"/institutions/{fake_id}",
        headers={
            "Content-Type": "application/json",
            "Authorization": "",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_institution_by_id_fails_for_non_admin(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.get(
            f"/institutions/{institution['id']}",
            headers=headers,
        )

    assert response.status_code == 403


# --- GET /institutions/_search ---


@pytest.mark.asyncio
async def test_search_institutions_returns_all_when_no_query(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    await _create_institution(async_test_client, headers)
    await _create_institution(async_test_client, headers)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/institutions/_search",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_search_institutions_filters_by_name(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    unique_name = f"UniqueSearchable {uuid4()}"
    await _create_institution(async_test_client, headers, name=unique_name)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/institutions/_search",
            params={"q": "UniqueSearchable"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(unique_name in inst["name"] for inst in data)


@pytest.mark.asyncio
async def test_search_institutions_is_case_insensitive(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    unique_name = f"CaseTestInst {uuid4()}"
    await _create_institution(async_test_client, headers, name=unique_name)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/institutions/_search",
            params={"q": "casetestinst"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) >= 1
    assert any("CaseTestInst" in inst["name"] for inst in data)


@pytest.mark.asyncio
async def test_search_institutions_returns_empty_for_no_match(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/institutions/_search",
            params={"q": f"nonexistent-{uuid4()}"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_search_institutions_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.get(
        "/institutions/_search",
        headers={
            "Content-Type": "application/json",
            "Authorization": "",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_institutions_fails_for_non_admin(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.get(
            "/institutions/_search",
            headers=headers,
        )

    assert response.status_code == 403
