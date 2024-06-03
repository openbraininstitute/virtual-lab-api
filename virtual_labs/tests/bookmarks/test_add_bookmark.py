import pytest
from httpx import AsyncClient

from virtual_labs.domain.bookmark import BookmarkCategory


@pytest.mark.asyncio
async def test_user_can_add_bookmark(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    payload = {
        "resource_id": "some-resource-id",
        "category": BookmarkCategory.ExperimentalNeuronMorphology.value,
    }

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resource_id"] == payload["resource_id"]
    assert data["category"] == payload["category"]
