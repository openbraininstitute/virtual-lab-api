import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.api import app
from virtual_labs.infrastructure.db.config import (
    default_session_factory,
    initialize_db,
    session_pool,
)
from virtual_labs.tests.utils import cleanup_resources, get_headers

VL_COUNT = 1
PROJECTS_PER_VL_COUNT = 2


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_database() -> None:
    """Initialize the database connection before running tests."""
    await initialize_db()


@asynccontextmanager
async def session_context_factory() -> AsyncGenerator[AsyncSession, None]:
    async with session_pool.session() as session:
        yield session


@pytest_asyncio.fixture()
async def async_test_client() -> AsyncGenerator[AsyncClient, None]:
    # default header used in this test client are for the user=test
    # if you need another test user please override the headers in the test
    headers = get_headers()
    async with AsyncClient(
        app=app,
        base_url="http://localhost:8000",
        headers=headers,
    ) as ac:
        yield ac


async_test_session = pytest_asyncio.fixture(default_session_factory)


@pytest_asyncio.fixture(scope="session", autouse=True)
def event_loop(request: Any) -> Any:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    headers = get_headers()

    # First, get existing labs for the user
    existing_labs_response = await client.get(
        "/virtual-labs",
        headers=headers,
    )

    # Clean up any existing labs
    if existing_labs_response.status_code == 200:
        existing_labs = (
            existing_labs_response.json().get("data", {}).get("virtual_labs", [])
        )
        for lab in existing_labs:
            lab_id = lab.get("id")
            if lab_id:
                try:
                    await cleanup_resources(client, lab_id)
                except Exception as e:
                    # Log the error but continue with the test
                    print(f"Error cleaning up existing lab {lab_id}: {e}")

    # Create a new lab
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
        "email_status": "verified",
    }

    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    yield response, headers

    # Clean up the newly created lab
    if (
        response.status_code == 200
        and response.json().get("data")
        and response.json()["data"].get("virtual_lab")
    ):
        lab_id = response.json()["data"]["virtual_lab"]["id"]
        await cleanup_resources(client, lab_id)
