import uuid
from http import HTTPStatus

import pytest
from httpx import AsyncClient, Response

from virtual_labs.domain.bookmark import EntityType
from virtual_labs.tests.utils import get_headers


async def request_to_add_bookmark(
    client: AsyncClient, lab_id: str, project_id: str, payload: dict[str, str | None]
) -> Response:
    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks",
        headers=get_headers(),
        json=payload,
    )
    return response


@pytest.mark.asyncio
async def test_user_can_add_bookmark(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    payload: dict[str, str | None] = {
        "entity_id": str(uuid.uuid4()),
        "category": EntityType.reconstruction_morphology.value,
    }

    response = await request_to_add_bookmark(client, lab_id, project_id, payload)

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["entity_id"] == payload["entity_id"]
    assert data["category"] == payload["category"]


@pytest.mark.asyncio
async def test_returns_error_if_resource_with_same_id_and_category_is_added_twice(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    payload: dict[str, str | None] = {
        "entity_id": str(uuid.uuid4()),
        "category": EntityType.reconstruction_morphology.value,
    }

    response1 = await request_to_add_bookmark(client, lab_id, project_id, payload)
    assert response1.status_code == HTTPStatus.OK

    response2 = await request_to_add_bookmark(client, lab_id, project_id, payload)
    assert response2.status_code == HTTPStatus.CONFLICT
    assert response2.json()["message"] == "Resource is already bookmarked in project"


@pytest.mark.asyncio
async def test_allows_adding_same_resource_to_different_category(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    payload: dict[str, str | None] = {
        "entity_id": str(uuid.uuid4()),
        "category": EntityType.reconstruction_morphology.value,
    }
    response1 = await request_to_add_bookmark(client, lab_id, project_id, payload)
    assert response1.status_code == HTTPStatus.OK

    response2 = await request_to_add_bookmark(
        client,
        lab_id,
        project_id,
        {
            "entity_id": str(uuid.uuid4()),
            "category": EntityType.electrical_cell_recording.value,
        },
    )
    assert response2.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_add_bookmark_with_entity_id(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    payload: dict[str, str | None] = {
        "entity_id": str(uuid.uuid4()),
        "category": EntityType.emodel.value,
    }

    response = await request_to_add_bookmark(client, lab_id, project_id, payload)

    assert response.status_code == HTTPStatus.OK
    response_json = response.json()
    data = response_json["data"]

    if "entityId" in data:
        assert data["entityId"] == payload["entity_id"]
    else:
        assert data["entity_id"] == payload["entity_id"]
    assert data["category"] == payload["category"]


@pytest.mark.asyncio
async def test_add_bookmark_with_entity_id_only(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    entity_id = str(uuid.uuid4())

    payload: dict[str, str | None] = {
        "entity_id": entity_id,
        "category": EntityType.single_neuron_simulation.value,
    }

    response = await request_to_add_bookmark(client, lab_id, project_id, payload)

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]

    assert data["entity_id"] == payload["entity_id"]
    assert data["category"] == payload["category"]
