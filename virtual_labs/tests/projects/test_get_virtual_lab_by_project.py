from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from virtual_labs.api import app
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import ENTITYCORE_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, str, dict[str, str]], None]:
    """Create a lab with a project and return (virtual_lab_id, project_id, headers)."""
    client = async_test_client
    headers = get_headers()

    lab_body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
        "email_status": "verified",
    }
    lab_response = await client.post("/virtual-labs", json=lab_body, headers=headers)
    assert lab_response.status_code == 200
    virtual_lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    project_body = {
        "name": f"Test Project {uuid4()}",
        "description": "Test Project",
    }
    project_response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json=project_body,
        headers=headers,
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["project"]["id"]

    yield virtual_lab_id, project_id, headers

    await cleanup_resources(client, virtual_lab_id)


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_forbidden_for_regular_user(
    async_test_client: AsyncClient,
    mock_lab_with_project: tuple[str, str, dict[str, str]],
) -> None:
    """Regular users should get 403 since they are not in the entitycore admin group."""
    _, project_id, headers = mock_lab_with_project

    response = await async_test_client.get(
        f"/virtual-labs/projects/{project_id}/virtual-lab",
        headers=headers,
    )
    assert response.status_code == 403
    error_data = response.json()
    assert error_data["error_code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_nonexistent_project_returns_403(
    async_test_client: AsyncClient,
) -> None:
    """Requesting a non-existent project should still return 403 for regular users
    because the admin auth check runs before the DB lookup."""
    headers = get_headers()
    fake_project_id = uuid4()

    response = await async_test_client.get(
        f"/virtual-labs/projects/{fake_project_id}/virtual-lab",
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_no_auth_returns_401(
    async_test_client: AsyncClient,
) -> None:
    """Requests without authentication should be rejected."""
    fake_project_id = uuid4()

    response = await async_test_client.get(
        f"/virtual-labs/projects/{fake_project_id}/virtual-lab",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_invalid_uuid_returns_422(
    async_test_client: AsyncClient,
) -> None:
    """An invalid UUID in the path should return 422 validation error."""
    headers = get_headers()

    response = await async_test_client.get(
        "/virtual-labs/projects/not-a-uuid/virtual-lab",
        headers=headers,
    )
    assert response.status_code == 422


# --- Mocked tests (no Keycloak / DB required) ---

FAKE_USER = AuthUser(
    sid="fake-sid",
    sub=str(uuid4()),
    preferred_username="admin-user",
    email="admin@test.org",
    email_verified=True,
    name="Admin User",
)
FAKE_TOKEN = "fake-token"


def _override_verify_jwt() -> tuple[AuthUser, str]:
    return (FAKE_USER, FAKE_TOKEN)


@pytest_asyncio.fixture
async def mocked_admin_client() -> AsyncGenerator[AsyncClient, None]:
    """Client with verify_jwt and session overridden so no real infra is needed."""
    from virtual_labs.infrastructure.db.config import default_session_factory

    app.dependency_overrides[verify_jwt] = _override_verify_jwt
    app.dependency_overrides[default_session_factory] = lambda: MagicMock()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_success_for_entitycore_admin(
    mocked_admin_client: AsyncClient,
) -> None:
    """An entitycore admin should get 200 with the correct project-to-vlab mapping."""
    project_id = uuid4()
    virtual_lab_id = uuid4()

    fake_project = MagicMock()
    fake_project.id = project_id
    fake_project.virtual_lab_id = virtual_lab_id

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.repositories.labs.get_virtual_lab_id_by_project_id",
            new_callable=AsyncMock,
            return_value=fake_project,
        ) as mock_repo,
    ):
        mock_kc.userinfo.return_value = {
            "groups": [ENTITYCORE_SERVICE_ADMIN_GROUP],
        }

        response = await mocked_admin_client.get(
            f"/virtual-labs/projects/{project_id}/virtual-lab",
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == str(project_id)
    assert data["virtual_lab_id"] == str(virtual_lab_id)
    mock_repo.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_forbidden_wrong_group(
    mocked_admin_client: AsyncClient,
) -> None:
    """A user in a different admin group (not entitycore) should get 403."""
    project_id = uuid4()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.return_value = {
            "groups": ["/service/some-other-service/admin"],
        }

        response = await mocked_admin_client.get(
            f"/virtual-labs/projects/{project_id}/virtual-lab",
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_get_virtual_lab_by_project_not_found_for_admin(
    mocked_admin_client: AsyncClient,
) -> None:
    """An entitycore admin requesting a non-existent project gets 403 because
    the verify_service_admin decorator catches unhandled exceptions as authorization errors."""
    from sqlalchemy.exc import NoResultFound

    fake_project_id = uuid4()

    with (
        patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc,
        patch(
            "virtual_labs.repositories.labs.get_virtual_lab_id_by_project_id",
            new_callable=AsyncMock,
            side_effect=NoResultFound(),
        ),
    ):
        mock_kc.userinfo.return_value = {
            "groups": [ENTITYCORE_SERVICE_ADMIN_GROUP],
        }

        response = await mocked_admin_client.get(
            f"/virtual-labs/projects/{fake_project_id}/virtual-lab",
        )

    # The decorator's generic exception handler wraps NoResultFound as a 403
    assert response.status_code == 403
    assert response.json()["error_code"] == "AUTHORIZATION_ERROR"
