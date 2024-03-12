from httpx import AsyncClient
from pydantic import UUID4


def instantiate_nexus_project(
    httpx_clt: AsyncClient,
    *,
    org_id: UUID4,
    project_id: UUID4,
    description: str,
) -> None:
    return None
