import asyncio
from typing import Any, AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.api import app


@pytest_asyncio.fixture()
async def async_test_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=app, base_url="http://localhost:8000") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session", autouse=True)
def event_loop(request: Any) -> Any:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
