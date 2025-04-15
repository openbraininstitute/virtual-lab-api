import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.domain.bookmark import BookmarkCategory
from virtual_labs.infrastructure.db.models import Bookmark
from virtual_labs.tests.utils import get_headers, session_context_factory

mock_core_bookmarks = [
    {
        "resource_id": "core-resource-1",
        "entity_id": uuid.UUID("5d3f4c97-85d5-476b-b6d3-26f2d7d11c5d"),
        "category": BookmarkCategory.ExperimentalNeuronMorphology.value,
    },
    {
        "resource_id": "core-resource-2",
        "entity_id": uuid.UUID("9fc94de5-3193-4f99-a9a6-74d20bc14ec2"),
        "category": BookmarkCategory.CircuitEModel.value,
    },
    {
        "resource_id": "core-resource-3",
        "entity_id": uuid.UUID("797e2ad0-01a3-4034-a117-9b44d7559bc1"),
        "category": BookmarkCategory.SingleNeuronSimulation.value,
    },
]


@pytest_asyncio.fixture
async def add_core_bookmarks_to_project(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> AsyncGenerator[tuple[str, str, dict[str, str], AsyncClient], None]:
    lab_id, project_id, headers, client = mock_create_project
    async with session_context_factory() as session:
        for bookmark in mock_core_bookmarks:
            session.add(
                Bookmark(
                    resource_id=bookmark["resource_id"],
                    entity_id=bookmark["entity_id"],
                    category=bookmark["category"],
                    project_id=project_id,
                )
            )

        await session.commit()
    yield lab_id, project_id, headers, client


@pytest.mark.asyncio
async def test_core_delete_bookmarks_success(
    add_core_bookmarks_to_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    """Test deleting multiple bookmarks via core_delete_bookmarks endpoint."""
    lab_id, project_id, headers, client = add_core_bookmarks_to_project

    bookmarks_to_delete = [
        {
            "resource_id": mock_core_bookmarks[0]["resource_id"],
            "entity_id": str(mock_core_bookmarks[0]["entity_id"]),
            "category": mock_core_bookmarks[0]["category"],
        },
        {
            "resource_id": mock_core_bookmarks[1]["resource_id"],
            "entity_id": str(mock_core_bookmarks[1]["entity_id"]),
            "category": mock_core_bookmarks[1]["category"],
        },
    ]

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks/delete",
        headers=get_headers(),
        json={"bookmarks": bookmarks_to_delete},
    )

    assert response.status_code == 200

    get_response = await client.get(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks",
        headers=get_headers(),
    )

    assert get_response.status_code == 200
    data = get_response.json()["data"]

    remaining_bookmarks = []
    for category, bookmarks in data.items():
        remaining_bookmarks.extend(bookmarks)

    assert len(remaining_bookmarks) == 1
    assert remaining_bookmarks[0]["resourceId"] == mock_core_bookmarks[2]["resource_id"]


@pytest.mark.asyncio
async def test_core_delete_bookmarks_with_nonexistent_entries(
    add_core_bookmarks_to_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    """Test core_delete_bookmarks handling when some bookmarks don't exist."""
    lab_id, project_id, headers, client = add_core_bookmarks_to_project

    bookmarks_to_delete = [
        {
            "resource_id": mock_core_bookmarks[0]["resource_id"],
            "entity_id": str(mock_core_bookmarks[0]["entity_id"]),
            "category": mock_core_bookmarks[0]["category"],
        },
        {
            "resource_id": "nonexistent-resource",
            "entity_id": str(uuid.uuid4()),
            "category": BookmarkCategory.SynaptomeSimulation.value,
        },
    ]

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks/delete",
        headers=get_headers(),
        json={"bookmarks": bookmarks_to_delete},
    )

    assert response.status_code == 200

    get_response = await client.get(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks",
        headers=get_headers(),
    )

    assert get_response.status_code == 200
    data = get_response.json()["data"]

    all_resource_ids = []
    for category, bookmarks in data.items():
        for bookmark in bookmarks:
            all_resource_ids.append(bookmark["resourceId"])

    assert mock_core_bookmarks[0]["resource_id"] not in all_resource_ids
    assert mock_core_bookmarks[1]["resource_id"] in all_resource_ids
    assert mock_core_bookmarks[2]["resource_id"] in all_resource_ids
