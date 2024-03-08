from typing import AsyncIterator

from httpx import AsyncClient


async def httpx_factory() -> AsyncIterator[AsyncClient]:
    client = AsyncClient(verify=False)
    try:
        yield client
    finally:
        await client.aclose()
