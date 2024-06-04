from http import HTTPStatus
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.domain.bookmark import AddBookmarkBody, BookmarkCategory
from virtual_labs.infrastructure.db.models import Bookmark
from virtual_labs.tests.utils import session_context_factory

mock_bookmark = AddBookmarkBody(
    resource_id="resource-1", category=BookmarkCategory.ExperimentalNeuronMorphology
)


@pytest_asyncio.fixture
async def add_bookmark_to_project(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> AsyncGenerator[tuple[str, str, dict[str, str], AsyncClient], None]:
    lab_id, project_id, headers, client = mock_create_project
    async with session_context_factory() as session:
        session.add(
            Bookmark(
                resource_id=mock_bookmark.resource_id,
                category=mock_bookmark.category.value,
                project_id=project_id,
            )
        )
        await session.commit()
    yield lab_id, project_id, headers, client


@pytest.mark.asyncio
async def test_user_can_delete_bookmarks_in_project(
    add_bookmark_to_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = add_bookmark_to_project

    delete_response = await client.delete(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks?resource_id={mock_bookmark.resource_id}&category={mock_bookmark.category.value}",
        headers=headers,
    )

    assert delete_response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_not_found_error_returned_when_user_deletes_bookmark_that_does_not_exist(
    mock_create_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = mock_create_project

    delete_response = await client.delete(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks?resource_id=whatever&category={mock_bookmark.category.value}",
        headers=headers,
    )

    assert delete_response.status_code == HTTPStatus.NOT_FOUND
