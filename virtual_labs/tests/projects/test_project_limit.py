"""Project cap: MAX_PROJECTS_PER_VIRTUAL_LAB live projects per lab, no per-user cap."""

import asyncio
from typing import AsyncGenerator, Callable, Coroutine
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select

from virtual_labs.infrastructure.db.models import Project
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.settings import Settings, settings
from virtual_labs.tests.utils import get_headers, session_context_factory

Filler = Callable[[int], Coroutine[None, None, None]]


async def _live_count(lab_id: UUID) -> int:
    async with session_context_factory() as session:
        return (
            await session.scalar(
                select(func.count(Project.id)).where(
                    Project.virtual_lab_id == lab_id, Project.deleted.is_(False)
                )
            )
        ) or 0


@pytest_asyncio.fixture
async def lab_filler(
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[UUID, Filler], None]:
    """Insert bare project rows (no KC groups) owned by `test`; removed before lab cleanup."""
    lab_id = UUID(mock_lab_create[0].json()["id"])
    owner_id = UUID(KeycloakRealm.get_user_id("test"))
    inserted: list[UUID] = []

    async def fill(n: int) -> None:
        async with session_context_factory() as session:
            for _ in range(n):
                pid = uuid4()
                session.add(
                    Project(
                        id=pid,
                        name=f"filler {pid}",
                        virtual_lab_id=lab_id,
                        owner_id=owner_id,
                        admin_group_id=f"filler-admin-{pid}",
                        member_group_id=f"filler-member-{pid}",
                    )
                )
                inserted.append(pid)
            await session.commit()

    yield lab_id, fill

    async with session_context_factory() as session:
        await session.execute(delete(Project).where(Project.id.in_(inserted)))
        await session.commit()


async def _create(client: AsyncClient, lab_id: UUID) -> Response:
    return await client.post(
        f"/virtual-labs/{lab_id}/projects",
        json={"name": f"Limit Project {uuid4()}", "description": "x"},
        headers=get_headers(),
    )


@pytest.mark.asyncio
async def test_lab_rejects_project_beyond_cap(
    async_test_client: AsyncClient, lab_filler: tuple[UUID, Filler]
) -> None:
    lab_id, fill = lab_filler
    cap = settings.MAX_PROJECTS_PER_VIRTUAL_LAB

    await fill(cap - 1)
    last = await _create(async_test_client, lab_id)
    assert last.status_code == 200, last.text

    over = await _create(async_test_client, lab_id)
    assert over.status_code == 400
    assert over.json()["error_code"] == "LIMIT_EXCEEDED"
    assert await _live_count(lab_id) == cap


@pytest.mark.asyncio
async def test_no_per_user_cap(
    async_test_client: AsyncClient, lab_filler: tuple[UUID, Filler]
) -> None:
    # the old rule capped a user at 20 owned projects; 50 must now be fine
    lab_id, fill = lab_filler
    await fill(50)
    response = await _create(async_test_client, lab_id)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_soft_deleted_projects_free_a_slot(
    async_test_client: AsyncClient, lab_filler: tuple[UUID, Filler]
) -> None:
    lab_id, fill = lab_filler
    await fill(settings.MAX_PROJECTS_PER_VIRTUAL_LAB - 1)
    project = await _create(async_test_client, lab_id)
    assert project.status_code == 200
    assert (await _create(async_test_client, lab_id)).status_code == 400

    deleted = await async_test_client.delete(
        f"/virtual-labs/{lab_id}/projects/{project.json()['id']}",
        headers=get_headers(),
    )
    assert deleted.status_code == 200, deleted.text
    assert (await _create(async_test_client, lab_id)).status_code == 200


@pytest.mark.asyncio
async def test_concurrent_creation_cannot_overshoot_cap(
    async_test_client: AsyncClient, lab_filler: tuple[UUID, Filler]
) -> None:
    lab_id, fill = lab_filler
    cap = settings.MAX_PROJECTS_PER_VIRTUAL_LAB
    await fill(cap - 1)

    # all three reach the guard; the lab row lock lets exactly one commit
    responses = await asyncio.gather(
        *(_create(async_test_client, lab_id) for _ in range(3))
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 400, 400], [r.text for r in responses]
    assert await _live_count(lab_id) == cap


@pytest.mark.asyncio
async def test_admin_restore_respects_cap(
    async_test_client: AsyncClient, lab_filler: tuple[UUID, Filler]
) -> None:
    lab_id, fill = lab_filler
    project = await _create(async_test_client, lab_id)
    project_id = project.json()["id"]
    admin = get_headers("test-service-admin")

    assert (
        await async_test_client.delete(f"/admin/projects/{project_id}", headers=admin)
    ).status_code == 200
    await fill(settings.MAX_PROJECTS_PER_VIRTUAL_LAB)

    restored = await async_test_client.post(
        f"/admin/projects/{project_id}/restore", headers=admin
    )
    assert restored.status_code == 400
    assert restored.json()["error_code"] == "LIMIT_EXCEEDED"


def test_cap_is_one_hundred_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The product rule, asserted on the code default and apart from the
    behaviour tests, so those can run against a lowered cap."""
    monkeypatch.delenv("MAX_PROJECTS_PER_VIRTUAL_LAB", raising=False)
    monkeypatch.delenv("MAX_PROJECTS_NUMBER", raising=False)
    assert Settings().MAX_PROJECTS_PER_VIRTUAL_LAB == 100


def test_pre_rename_env_key_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    """`extra="allow"` would swallow the old key silently; the alias keeps a
    deployment that still sets MAX_PROJECTS_NUMBER in effect."""
    monkeypatch.setenv("MAX_PROJECTS_NUMBER", "7")
    assert Settings().MAX_PROJECTS_PER_VIRTUAL_LAB == 7
