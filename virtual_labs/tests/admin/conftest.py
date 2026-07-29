from typing import AsyncGenerator, Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab_with_project,
    get_headers,
)

# the fixture lab is owned by `test-1` while the admin/maintainer act
# through the service groups — proving the endpoints are not
# membership-gated
LAB_OWNER = "test-1"


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return get_headers("test-service-admin")


@pytest.fixture
def maintainer_headers() -> dict[str, str]:
    return get_headers("test-service-maintainer")


@pytest.fixture
def user_headers() -> dict[str, str]:
    return get_headers("test")


@pytest_asyncio.fixture
async def lab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[dict[str, Any], str], None]:
    lab, project_id = await create_mock_lab_with_project(
        async_test_client, owner_username=LAB_OWNER
    )
    yield lab, project_id
    await cleanup_resources(async_test_client, lab["id"], user=LAB_OWNER)
