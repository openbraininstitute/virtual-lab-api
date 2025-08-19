import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.domain.bookmark import EntityType
from virtual_labs.infrastructure.db.models import Bookmark
from virtual_labs.tests.utils import get_headers, session_context_factory

mock_core_bookmarks = [
    {
        "entity_id": uuid.UUID("5d3f4c97-85d5-476b-b6d3-26f2d7d11c5d"),
        "category": EntityType.reconstruction_morphology.value,
    },
    {
        "entity_id": uuid.UUID("9fc94de5-3193-4f99-a9a6-74d20bc14ec2"),
        "category": EntityType.emodel.value,
    },
    {
        "entity_id": uuid.UUID("797e2ad0-01a3-4034-a117-9b44d7559bc1"),
        "category": EntityType.single_neuron_simulation.value,
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
            "entity_id": str(mock_core_bookmarks[0]["entity_id"]),
            "category": mock_core_bookmarks[0]["category"],
        },
        {
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
    assert remaining_bookmarks[0]["entity_id"] == str(
        mock_core_bookmarks[2]["entity_id"]
    )


@pytest.mark.asyncio
async def test_core_delete_bookmarks_with_nonexistent_entries(
    add_core_bookmarks_to_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    """Test core_delete_bookmarks handling when some bookmarks don't exist."""
    lab_id, project_id, headers, client = add_core_bookmarks_to_project

    bookmarks_to_delete = [
        {
            "entity_id": str(uuid.UUID("5d3f4c97-85d5-476b-b6d3-26f2d7d11c3d")),
            "category": mock_core_bookmarks[0]["category"],
        }
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

    all_entity_ids = []
    for category, bookmarks in data.items():
        for bookmark in bookmarks:
            all_entity_ids.append(bookmark["entity_id"])

    assert str(mock_core_bookmarks[1]["entity_id"]) in all_entity_ids
    assert str(mock_core_bookmarks[2]["entity_id"]) in all_entity_ids
