import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.domain.bookmark import BookmarkIn, EntityType
from virtual_labs.infrastructure.db.models import Bookmark
from virtual_labs.tests.utils import session_context_factory

mock_bookmarks: list[BookmarkIn] = [
    BookmarkIn(
        entity_id=uuid.UUID("4d2f4c97-85d5-476b-b6d3-26f2d7d11c5d"),
        category=EntityType.reconstruction_morphology,
    ),
    BookmarkIn(
        entity_id=uuid.UUID("8fc94de5-3193-4f99-a9a6-74d20bc14ec2"),
        category=EntityType.reconstruction_morphology,
    ),
    BookmarkIn(
        entity_id=uuid.UUID("697e2ad0-01a3-4034-a117-9b44d7559bc1"),
        category=EntityType.electrical_cell_recording,
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
                    entity_id=bookmark.entity_id,
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
            "entity_id": str(mock_bookmarks[1].entity_id),
            "category": mock_bookmarks[1].category.value,
        },
        {
            "entity_id": str(mock_bookmarks[2].entity_id),
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

    assert data["failed_to_delete"] == []
    assert data["successfully_deleted"] == [
        {
            "entity_id": str(mock_bookmarks[1].entity_id),
            "category": mock_bookmarks[1].category.value,
        },
        {
            "entity_id": str(mock_bookmarks[2].entity_id),
            "category": mock_bookmarks[2].category.value,
        },
    ]
