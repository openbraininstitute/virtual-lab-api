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
    BookmarkIn(
        entity_id=uuid.UUID("3ec74b91-3f33-442f-bdc1-b3859f8232b1"),
        category=EntityType.experimental_bouton_density,
    ),
    BookmarkIn(
        entity_id=uuid.UUID("e637a438-eeb1-4d11-95cd-e5d4e083f9e7"),
        category=EntityType.experimental_bouton_density,
    ),
    BookmarkIn(
        entity_id=uuid.UUID("109f3405-2b8a-4c34-85d6-14b17968441d"),
        category=EntityType.experimental_neuron_density,
    ),
    BookmarkIn(
        entity_id=uuid.UUID("98b21266-c52b-4c77-926e-56a197d3bbd6"),
        category=EntityType.experimental_neuron_density,
    ),
    BookmarkIn(
        entity_id=uuid.UUID("491afad6-2fbd-4a03-a86d-e58a5d9cbf7b"),
        category=EntityType.reconstruction_morphology,
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
                    category=bookmark.category,
                    project_id=project_id,
                )
            )

        await session.commit()
    yield lab_id, project_id, headers, client


@pytest.mark.asyncio
async def test_user_can_get_all_project_bookmarks_by_type(
    add_bookmarks_to_project: tuple[str, str, dict[str, str], AsyncClient],
) -> None:
    lab_id, project_id, headers, client = add_bookmarks_to_project

    response = await client.get(
        f"/virtual-labs/{lab_id}/projects/{project_id}/bookmarks",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]

    assert len(data[EntityType.reconstruction_morphology.value]) == 3
    assert len(data[EntityType.experimental_bouton_density.value]) == 2
    assert len(data[EntityType.experimental_neuron_density.value]) == 2
    assert len(data[EntityType.electrical_cell_recording.value]) == 1
    assert data.get(EntityType.experimental_synapses_per_connection.value) is None
