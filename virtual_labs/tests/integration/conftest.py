from http import HTTPStatus
from typing import Any, AsyncGenerator, Dict, Tuple

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.infrastructure.kc.config import kc_realm
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
)


# Fixture to get test user IDs from Keycloak
@pytest.fixture(scope="module")
def test_user_ids() -> Dict[str, str]:
    """Retrieves IDs for predefined test users from Keycloak."""
    ids: Dict[str, str] = {}
    for i in range(8):  # test, test-1, test-2, test-3, test-4
        username = f"test-{i}" if i > 0 else "test"
        try:
            user = kc_realm.get_users({"username": username})
            if user:
                ids[username] = user[0]["id"]
            else:
                pytest.fail(f"Required test user '{username}' not found in Keycloak.")
        except Exception as e:
            pytest.fail(f"Failed to get user ID for {username}: {e}")
    return ids


@pytest_asyncio.fixture
async def created_lab(
    async_test_client: AsyncClient,
    test_user_ids: Dict[str, str],
    request: Any,
) -> AsyncGenerator[Tuple[str, Dict[str, Any], str], None]:
    owner_username = getattr(request, "param", "test")
    if owner_username not in test_user_ids:
        pytest.fail(
            f"Username '{owner_username}' provided via param is not in test_user_ids fixture."
        )

    owner_id = test_user_ids[owner_username]

    response = await create_mock_lab(async_test_client, owner_username=owner_username)

    if response.status_code != HTTPStatus.OK:
        pytest.fail(
            f"Failed to create lab for user '{owner_username}'. Status: {response.status_code}. Response: {response.text}"
        )

    lab_data = response.json()["data"]["virtual_lab"]
    lab_id = lab_data["id"]

    yield (
        lab_id,
        lab_data,
        owner_id,
    )
    try:
        await cleanup_resources(async_test_client, lab_id, owner_username)
    except Exception as e:
        print(f"Error during cleanup for lab {lab_id}: {e}")
