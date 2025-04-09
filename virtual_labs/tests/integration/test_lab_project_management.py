from http import HTTPStatus
from typing import Any, AsyncGenerator, Dict, List, Tuple
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from virtual_labs.infrastructure.db.models import Project, Subscription, VirtualLab
from virtual_labs.infrastructure.kc.config import kc_realm
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
    get_headers,
    session_context_factory,
)

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def test_user_ids() -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for i in range(8):
        username = f"test-{i}" if i > 0 else "test"
        try:
            user = kc_realm.get_users({"username": username})
            if user:
                ids[username] = user[0]["id"]
            else:
                pytest.fail(f"Test user {username} not found in Keycloak.")
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


@pytest_asyncio.fixture
async def created_project(
    async_test_client: AsyncClient,
    created_lab: Tuple[str, Dict[str, Any], str],
    test_user_ids: Dict[str, str],
) -> AsyncGenerator[Tuple[str, str, str, Project, Dict[str, str]], None]:
    lab_id, lab_data, owner_id = created_lab
    owner_username = "test"
    headers = get_headers(owner_username)
    gqr = GroupQueryRepository()
    umr = UserMutationRepository()

    async with session_context_factory() as session:
        db_lab = await session.get(VirtualLab, UUID(lab_id))

    # Ensure db_lab is not None before accessing attributes
    if db_lab is None:
        pytest.fail(f"Virtual lab with ID {lab_id} not found in database")
        # This line will never be executed but helps type checking
        return

    vl_admin_group_id = str(db_lab.admin_group_id)
    vl_member_group_id = str(db_lab.member_group_id)

    try:
        vl_admins = await gqr.a_retrieve_group_user_ids(vl_admin_group_id)
        if test_user_ids["test-1"] not in vl_admins:
            await umr.a_attach_user_to_group(
                user_id=UUID(test_user_ids["test-1"]), group_id=vl_admin_group_id
            )

        vl_members = await gqr.a_retrieve_group_user_ids(vl_member_group_id)
        if test_user_ids["test-2"] not in vl_members:
            await umr.a_attach_user_to_group(
                user_id=UUID(test_user_ids["test-2"]), group_id=vl_member_group_id
            )
        if test_user_ids["test-3"] not in vl_members:
            await umr.a_attach_user_to_group(
                user_id=UUID(test_user_ids["test-3"]), group_id=vl_member_group_id
            )

    except Exception as e:
        print(f"Warning: Could not add users to VL groups in fixture setup: {e}")

    project_name = f"Test Project {uuid4()}"
    project_body = {
        "name": project_name,
        "description": "Project for Attach User Test",
    }
    project_response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/projects",
        json=project_body,
        headers=headers,
    )

    assert (
        project_response.status_code == HTTPStatus.OK
    ), f"Failed to create project: {project_response.text}"

    project_id = project_response.json()["data"]["project"]["id"]
    async with session_context_factory() as session:
        project_data = await session.get(Project, UUID(project_id))

    # Ensure project_data is not None before yielding
    if project_data is None:
        pytest.fail(f"Project with ID {project_id} not found in database")
        # This line will never be executed but helps type checking
        return

    yield (
        lab_id,
        project_id,
        owner_id,
        project_data,
        test_user_ids,
    )


class TestVirtualLabCreation:
    async def test_create_virtual_lab_success(
        self, async_test_client: AsyncClient, test_user_ids: Dict[str, str]
    ) -> None:
        owner_username = "test-1"
        owner_id = test_user_ids[owner_username]
        lab_name = f"Test Success Lab {uuid4()}"
        body = {
            "name": lab_name,
            "description": "Test Success Description",
            "reference_email": f"{owner_username}@test.org",
            "entity": "Test University",
            "email_status": "verified",
        }
        headers = get_headers(owner_username)

        response = await async_test_client.post(
            "/virtual-labs",
            json=body,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()["data"]
        created_lab_data = response_data["virtual_lab"]
        lab_id = created_lab_data["id"]

        try:
            # Assert response structure (basic check)
            assert "virtual_lab" in response_data
            assert created_lab_data["name"] == lab_name

            # Assert DB record
            async with session_context_factory() as session:
                db_lab = await session.get(VirtualLab, UUID(lab_id))
                assert db_lab is not None
                assert str(db_lab.id) == lab_id
                assert str(db_lab.owner_id) == owner_id
                assert db_lab.name == lab_name
                assert db_lab.description == body["description"]
                assert db_lab.reference_email == body["reference_email"]

                # Assert Free Subscription creation
                stmt = select(Subscription).where(
                    Subscription.virtual_lab_id == UUID(lab_id)
                )
                db_sub = (await session.execute(stmt)).scalar_one_or_none()
                assert db_sub is not None
                assert db_sub.user_id == UUID(owner_id)
                assert db_sub.subscription_type == "FREE"

            # Assert Keycloak groups and owner membership
            print("-->", db_lab.__dict__)
            gqr = GroupQueryRepository()
            admin_group_id = str(db_lab.admin_group_id)
            member_group_id = str(db_lab.member_group_id)

            admin_group_users = await gqr.a_retrieve_group_user_ids(admin_group_id)
            member_group_users = await gqr.a_retrieve_group_user_ids(member_group_id)

            assert owner_id in admin_group_users
            assert owner_id not in member_group_users

        finally:
            # Cleanup created resources
            await cleanup_resources(async_test_client, lab_id, owner_username)

    @pytest.mark.parametrize("created_lab", ["test-1"], indirect=True)
    async def test_create_virtual_lab_duplicate_name(
        self,
        async_test_client: AsyncClient,
        created_lab: Tuple[str, Dict[str, Any], str],
    ) -> None:
        lab_id, lab_data, owner_id = created_lab
        owner_username = "test"

        body = {
            "name": lab_data["name"],
            "description": "Duplicate Test",
            "reference_email": "test@test.org",
            "entity": "EPFL",
            "email_status": "verified",
        }
        headers = get_headers(owner_username)
        response = await async_test_client.post(
            "/virtual-labs",
            json=body,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.CONFLICT
        error_data = response.json()
        assert error_data["error_code"] == "ENTITY_ALREADY_EXISTS"
        assert (
            "Another virtual lab with same name already exists" in error_data["message"]
        )

    async def test_create_virtual_lab_owner_already_has_lab(
        self,
        async_test_client: AsyncClient,
        created_lab: Tuple[str, Dict[str, Any], str],
    ) -> None:
        lab_id, lab_data, owner_id = created_lab
        owner_username = "test"

        body = {
            "name": f"Second Lab {uuid4()}",
            "description": "Second Lab Test",
            "reference_email": "test@test.org",
            "entity": "EPFL",
            "email_status": "verified",
        }
        headers = get_headers(owner_username)
        response = await async_test_client.post(
            "/virtual-labs",
            json=body,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()
        assert error_data["error_code"] == "ENTITY_ALREADY_EXISTS"
        assert "User already have a virtual lab" in error_data["message"]

    async def test_create_virtual_lab_unverified_email(
        self, async_test_client: AsyncClient, test_user_ids: Dict[str, str]
    ) -> None:
        owner_username = "test-2"
        lab_name = f"Unverified Email Lab {uuid4()}"
        body = {
            "name": lab_name,
            "description": "Unverified Email Test",
            "reference_email": f"{owner_username}@test.org",
            "entity": "Test Institute",
            "email_status": "registered",
        }
        headers = get_headers(owner_username)
        response = await async_test_client.post(
            "/virtual-labs",
            json=body,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        error_data = response.json()

        assert error_data["error_code"] == "INVALID_REQUEST"
        assert "Email must be verified to create a virtual lab" in error_data["message"]

    async def test_create_virtual_lab_missing_name(
        self, async_test_client: AsyncClient, test_user_ids: Dict[str, str]
    ) -> None:
        owner_username = "test-3"
        body = {
            # "name": "Missing Name Lab", # Name is missing
            "description": "Missing Name Test",
            "reference_email": f"{owner_username}@test.org",
            "entity": "Test Co",
            "email_status": "verified",
        }
        headers = get_headers(owner_username)
        response = await async_test_client.post(
            "/virtual-labs",
            json=body,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestAttachUsersToProject:
    async def test_attach_users_initial_success(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"
        gqr = GroupQueryRepository()
        proj_admin_group_id = str(project_data.admin_group_id)
        proj_member_group_id = str(project_data.member_group_id)

        users_to_attach: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {"id": user_ids["test-1"], "email": "test-1@test.org", "role": "admin"},
                {
                    "id": user_ids["test-2"],
                    "email": "test-2@test.org",
                    "role": "member",
                },
            ]
        }
        attach_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=users_to_attach,
            headers=get_headers(owner_username),
        )

        assert attach_response.status_code == HTTPStatus.OK
        response_data = attach_response.json()["data"]

        # Assert response structure
        assert len(response_data["added_users"]) == 2
        assert len(response_data["updated_users"]) == 0
        assert len(response_data["failed_operations"]) == 0
        assert len(response_data["email_sending_failures"]) == 0

        added_user_ids_roles = {
            u["id"]: u["role"] for u in response_data["added_users"]
        }
        assert added_user_ids_roles[user_ids["test-1"]] == "admin"
        assert added_user_ids_roles[user_ids["test-2"]] == "member"

        proj_admins = await gqr.a_retrieve_group_user_ids(proj_admin_group_id)
        proj_members = await gqr.a_retrieve_group_user_ids(proj_member_group_id)

        assert user_ids["test-1"] in proj_admins
        assert user_ids["test-1"] not in proj_members

        assert user_ids["test-2"] in proj_members
        assert user_ids["test-2"] not in proj_admins

        assert owner_id in proj_admins

    async def test_attach_users_update_role(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"
        gqr = GroupQueryRepository()
        # Convert Column type to str
        proj_admin_group_id = str(project_data.admin_group_id)
        proj_member_group_id = str(project_data.member_group_id)

        # First, add users with initial roles
        initial_users: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {"id": user_ids["test-1"], "email": "test-1@test.org", "role": "admin"},
                {
                    "id": user_ids["test-2"],
                    "email": "test-2@test.org",
                    "role": "member",
                },
            ]
        }
        await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=initial_users,
            headers=get_headers(owner_username),
        )

        updated_users: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {
                    "id": user_ids["test-1"],
                    "email": "test-1@test.org",
                    "role": "member",
                },  # Admin -> Member
                {
                    "id": user_ids["test-2"],
                    "email": "test-2@test.org",
                    "role": "admin",
                },  # Member -> Admin
            ]
        }
        update_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=updated_users,
            headers=get_headers(owner_username),
        )

        assert update_response.status_code == HTTPStatus.OK
        response_data = update_response.json()["data"]

        assert len(response_data["added_users"]) == 0
        assert len(response_data["updated_users"]) == 2
        assert len(response_data["failed_operations"]) == 0

        updated_user_ids_roles = {
            u["id"]: u["role"] for u in response_data["updated_users"]
        }
        assert updated_user_ids_roles[user_ids["test-1"]] == "member"
        assert updated_user_ids_roles[user_ids["test-2"]] == "admin"

        proj_admins = await gqr.a_retrieve_group_user_ids(proj_admin_group_id)
        proj_members = await gqr.a_retrieve_group_user_ids(proj_member_group_id)

        assert user_ids["test-1"] in proj_members
        assert user_ids["test-1"] not in proj_admins

        assert user_ids["test-2"] in proj_admins
        assert user_ids["test-2"] not in proj_members

    async def test_attach_user_already_member_same_role(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"
        gqr = GroupQueryRepository()
        proj_member_group_id = str(project_data.member_group_id)

        # Add test-3 as member initially
        initial_users: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {"id": user_ids["test-3"], "email": "test-3@test.org", "role": "member"}
            ]
        }
        initial_resp = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=initial_users,
            headers=get_headers(owner_username),
        )
        assert initial_resp.status_code == HTTPStatus.OK
        assert len(initial_resp.json()["data"]["added_users"]) == 1

        # Attach test-3 as member again
        reattach_users: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {"id": user_ids["test-3"], "email": "test-3@test.org", "role": "member"}
            ]
        }
        reattach_resp = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=reattach_users,
            headers=get_headers(owner_username),
        )
        assert reattach_resp.status_code == HTTPStatus.OK
        response_data = reattach_resp.json()["data"]

        # Assert nothing changed in the response
        assert len(response_data["added_users"]) == 0
        assert len(response_data["updated_users"]) == 0
        assert len(response_data["failed_operations"]) == 0

        # Assert Keycloak state remains the same
        proj_members = await gqr.a_retrieve_group_user_ids(proj_member_group_id)
        assert user_ids["test-3"] in proj_members

    async def test_attach_user_not_in_vlab_fails(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"

        # Assume test-5 is NOT part of the Virtual Lab (fixture only adds 1, 2, 3)
        users_to_attach: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {
                    "id": user_ids["test-5"],
                    "email": "test-5@test.org",
                    "role": "member",
                },
            ]
        }
        attach_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=users_to_attach,
            headers=get_headers(owner_username),
        )

        # This should fail because the user isn't in the parent VL
        assert attach_response.status_code == HTTPStatus.BAD_REQUEST
        error_data = attach_response.json()
        assert error_data["error_code"] == "INVALID_REQUEST"
        assert (
            "One or more users are not members of the parent Virtual Lab"
            in error_data["message"]
        )
        assert "users_not_in_virtual_lab" in error_data["data"]
        assert user_ids["test-5"] in error_data["data"]["users_not_in_virtual_lab"]

    async def test_attach_owner_fails_silently(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"
        gqr = GroupQueryRepository()
        proj_admin_group_id = str(project_data.admin_group_id)

        # Try to attach the owner (test user) again, maybe with a different role
        users_to_attach: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {
                    "id": owner_id,
                    "email": "test@test.org",
                    "role": "member",
                },  # Try changing owner role
            ]
        }
        attach_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=users_to_attach,
            headers=get_headers(owner_username),
        )

        # The use case filters out the owner, so it should succeed with no operations performed
        assert attach_response.status_code == HTTPStatus.OK
        response_data = attach_response.json()["data"]
        assert len(response_data["added_users"]) == 0
        assert len(response_data["updated_users"]) == 0
        assert len(response_data["failed_operations"]) == 0
        assert (
            "No unique, non-owner users provided to process"
            in attach_response.json()["message"]
        )

        # Assert owner is still admin in Keycloak
        proj_admins = await gqr.a_retrieve_group_user_ids(proj_admin_group_id)
        assert owner_id in proj_admins

    async def test_attach_users_empty_list(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"

        users_to_attach: Dict[str, List[Dict[str, str]]] = {"users": []}
        attach_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=users_to_attach,
            headers=get_headers(owner_username),
        )

        assert attach_response.status_code == HTTPStatus.OK
        response_data = attach_response.json()["data"]
        assert len(response_data["added_users"]) == 0
        assert len(response_data["updated_users"]) == 0
        assert len(response_data["failed_operations"]) == 0
        assert (
            "No unique, non-owner users provided to process"
            in attach_response.json()["message"]
        )

    async def test_attach_users_non_admin_fails(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        non_admin_username = (
            "test-3"  # Added to VL as member, but not project admin initially
        )

        # Ensure test-3 is only a member of the VL (done in fixture),
        # not project admin initially
        users_to_attach: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {"id": user_ids["test-4"], "email": "test-4@test.org", "role": "member"}
            ]
        }
        attach_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=users_to_attach,
            headers=get_headers(non_admin_username),
        )
        assert attach_response.status_code == HTTPStatus.FORBIDDEN
