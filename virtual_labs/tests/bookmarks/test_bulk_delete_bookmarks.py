import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.domain.bookmark import BookmarkCategory, BookmarkIn
from virtual_labs.infrastructure.db.models import Bookmark
from virtual_labs.tests.utils import session_context_factory

mock_bookmarks: list[BookmarkIn] = [
    BookmarkIn(
        resource_id="resource-1",
        entity_id=uuid.UUID("4d2f4c97-85d5-476b-b6d3-26f2d7d11c5d"),
        category=BookmarkCategory.ExperimentalNeuronMorphology,
    ),
    BookmarkIn(
        resource_id="resource-2",
        entity_id=uuid.UUID("8fc94de5-3193-4f99-a9a6-74d20bc14ec2"),
        category=BookmarkCategory.ExperimentalNeuronMorphology,
    ),
    BookmarkIn(
        resource_id="resource-3",
        entity_id=uuid.UUID("697e2ad0-01a3-4034-a117-9b44d7559bc1"),
        category=BookmarkCategory.ExperimentalElectroPhysiology,
    ),
]


@pytest_asyncio.fixture
async def add_bookmarks_to_project(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> AsyncGenerator[tuple[str, str, dict[str, str], AsyncClient], None]:
    lab_id, project_id, headers, client = mock_create_project
    async with session_context_factory() as session:
        for bookmark in mock_bookmarks:
            session.add(
                Bookmark(
                    resource_id=bookmark.resource_id,
                    category=bookmark.category.value,
                    project_id=project_id,
                )
            )

        await session.commit()
    yield lab_id, project_id, headers, client


@pytest.mark.asyncio
async def test_user_can_bulk_delete_bookmarks_in_project(
    add_bookmarks_to_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = add_bookmarks_to_project
    bookmarks_to_delete = [
        {
            "resourceId": mock_bookmarks[1].resource_id,
            "entity_id": None,
            "category": mock_bookmarks[1].category.value,
        },
        {
            "resourceId": "non_existing_resource",
            "entity_id": None,
            "category": mock_bookmarks[1].category.value,
        },
        {
            "resourceId": mock_bookmarks[2].resource_id,
            "entity_id": None,
            "category": mock_bookmarks[2].category.value,
        },
    ]

    bulk_delete_response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks/bulk-delete",
        headers=headers,
        json=bookmarks_to_delete,
    )

    assert bulk_delete_response.status_code == 200
    data = bulk_delete_response.json()["data"]

    assert data["failed_to_delete"] == [bookmarks_to_delete[1]]
    assert data["successfully_deleted"] == [
        bookmarks_to_delete[0],
        bookmarks_to_delete[2],
    ]
