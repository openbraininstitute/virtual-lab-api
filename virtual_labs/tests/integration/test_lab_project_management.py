from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, AsyncGenerator, Dict, List, Tuple, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from loguru import logger
from sqlalchemy import select

from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    Project,
    StripeUser,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionTierEnum,
    VirtualLab,
)
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository
from virtual_labs.tests.utils import (
    cleanup_all_user_labs,
    cleanup_resources,
    get_headers,
    session_context_factory,
)

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


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
    owner_uuid = UUID(owner_id)  # Define owner_uuid early

    async with session_context_factory() as session:
        db_lab = await session.get(VirtualLab, UUID(lab_id))
        if not db_lab:
            pytest.fail("Failed to retrieve created lab from DB.")

        stmt_check_sub = select(Subscription).where(
            Subscription.user_id == owner_uuid,
            Subscription.virtual_lab_id == db_lab.id,
            Subscription.type == "paid",
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        existing_sub = (await session.execute(stmt_check_sub)).scalar_one_or_none()

        if not existing_sub:
            logger.debug(
                f"Creating paid subscription for owner {owner_id} / lab {str(lab_id)}"
            )
            stmt_tier = select(SubscriptionTier).where(
                SubscriptionTier.tier == SubscriptionTierEnum.PRO
            )
            tier = (await session.execute(stmt_tier)).scalar_one_or_none()
            if not tier:
                pytest.fail("PRO Subscription Tier not found. Seed DB?")

            stmt_stripe_user = select(StripeUser).where(
                StripeUser.user_id == owner_uuid
            )
            stripe_user = (await session.execute(stmt_stripe_user)).scalar_one_or_none()
            if not stripe_user:
                customer_id = f"cus_test_{uuid4()}"
                stripe_user = StripeUser(
                    user_id=owner_uuid, stripe_customer_id=customer_id
                )
                session.add(stripe_user)
                await session.flush()
            else:
                customer_id = (
                    stripe_user.stripe_customer_id
                    if stripe_user.stripe_customer_id is not None
                    else ""
                )

            now = datetime.now()
            # Ensure customer_id is str
            customer_id = cast(str, stripe_user.stripe_customer_id)

            price_id: str = (
                tier.stripe_monthly_price_id
                if tier.stripe_monthly_price_id is not None
                else f"price_test_{uuid4()}"
            )

            paid_sub = PaidSubscription(
                user_id=owner_uuid,
                virtual_lab_id=db_lab.id,
                tier_id=tier.id,
                subscription_type=tier.tier,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                type="paid",
                stripe_subscription_id=f"sub_test_{uuid4()}",
                stripe_price_id=price_id,
                customer_id=customer_id,
                cancel_at_period_end=False,
                amount=tier.monthly_amount or 0,
                currency=tier.currency or "chf",
                interval="month",
                auto_renew=True,
            )
            session.add(paid_sub)
            logger.debug(f"Committed paid subscription {paid_sub.id}")
            await session.commit()
            await session.refresh(db_lab)
        else:
            logger.debug(
                f"Found existing active paid sub {existing_sub.id} for owner {owner_id}"
            )

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

    assert project_response.status_code == HTTPStatus.OK, (
        f"Failed to create project: {project_response.text}"
    )

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
        assert len(response_data["added_users"]) == 1
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
        assert "No users to process." in attach_response.json()["message"]

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
        assert "No users to process." in attach_response.json()["message"]

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

    async def test_attach_users_no_paid_subscription_fails(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        """
        Tests that attaching users fails with FORBIDDEN if the requesting user
        (project owner/admin in this case) does not have an active 'paid' subscription.
        """
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"
        owner_uuid = UUID(owner_id)

        # Remove the paid subscription potentially created by the fixture
        async with session_context_factory() as session:
            stmt = select(PaidSubscription).where(
                PaidSubscription.user_id == owner_uuid,
                PaidSubscription.virtual_lab_id
                == UUID(lab_id),  # Ensure we target the right lab's sub
                PaidSubscription.type == "paid",
                PaidSubscription.status == SubscriptionStatus.ACTIVE,
            )
            sub_to_delete = (await session.execute(stmt)).scalar_one_or_none()

            if sub_to_delete:
                logger.info(f"Deleting subscription {sub_to_delete.id} for test")
                await session.delete(sub_to_delete)
                await session.commit()
            else:
                logger.warning(
                    f"No active paid subscription found for user {owner_id} / lab {lab_id} to delete for test."
                )

        users_to_attach: Dict[str, List[Dict[str, str]]] = {
            "users": [
                {"id": user_ids["test-1"], "email": "test-1@test.org", "role": "admin"},
            ]
        }

        attach_response = await async_test_client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/users/attach",
            json=users_to_attach,
            headers=get_headers(owner_username),
        )

        assert attach_response.status_code == HTTPStatus.FORBIDDEN
        error_data = attach_response.json()
        assert error_data["error_code"] == "FORBIDDEN_OPERATION"
        assert "User does not have an active subscription" in error_data["message"]

    async def test_attach_users_canceled_subscription_fails(
        self,
        async_test_client: AsyncClient,
        created_project: Tuple[str, str, str, Project, Dict[str, str]],
    ) -> None:
        """
        tests that attaching users fails with FORBIDDEN if the requesting user
        has a paid subscription, but its status is not 'active' (e.g., 'canceled').
        """
        lab_id, project_id, owner_id, project_data, user_ids = created_project
        owner_username = "test"
        owner_uuid = UUID(owner_id)

        # Find the paid subscription and update its status to canceled
        async with session_context_factory() as session:
            stmt = select(PaidSubscription).where(
                PaidSubscription.user_id == owner_uuid,
                PaidSubscription.virtual_lab_id == UUID(lab_id),
                PaidSubscription.type == "paid",
                PaidSubscription.status
                == SubscriptionStatus.ACTIVE,  # Find the active one first
            )
            sub_to_update = (await session.execute(stmt)).scalar_one_or_none()

            if sub_to_update:
                logger.info(
                    f"Updating subscription {sub_to_update.id} status to CANCELED for test"
                )
                sub_to_update.status = SubscriptionStatus.CANCELED
                session.add(sub_to_update)
                await session.commit()
            else:
                pytest.fail(
                    f"Could not find the active paid subscription for user {owner_id} / lab {lab_id} created by fixture."
                )

        users_to_attach: Dict[str, List[Dict[str, str]]] = {
            "users": [
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

        assert attach_response.status_code == HTTPStatus.FORBIDDEN
        error_data = attach_response.json()
        assert error_data["error_code"] == "FORBIDDEN_OPERATION"
        assert "User does not have an active subscription" in error_data["message"]

    async def test_create_project_adds_creator_to_vlab_member_group(
        self,
        async_test_client: AsyncClient,
        test_user_ids: Dict[str, str],
    ) -> None:
        """
        tests that when a user creates a new project, they are added to both
        the project admin group and the virtual lab member group.
        """
        client = async_test_client
        owner_username = "test-5"
        owner_id = test_user_ids[owner_username]

        await cleanup_all_user_labs(client=client, username=owner_username)

        # create a virtual lab
        lab_name = f"Test VL for Project Creation {uuid4()}"
        lab_body = {
            "name": lab_name,
            "description": "Test virtual lab for project creation",
            "reference_email": f"{owner_username}@test.org",
            "entity": "Test University",
            "email_status": "verified",
        }
        lab_response = await client.post(
            "/virtual-labs",
            json=lab_body,
            headers=get_headers(owner_username),
        )
        assert lab_response.status_code == HTTPStatus.OK
        lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

        gqr = GroupQueryRepository()

        # get virtual lab member group ID
        async with session_context_factory() as session:
            db_lab = await session.get(VirtualLab, UUID(lab_id))
            if not db_lab:
                pytest.fail("Failed to retrieve created lab from DB.")
            vl_member_group_id = str(db_lab.member_group_id)

        # create a project
        project_name = f"Test Project Creation {uuid4()}"
        project_body = {
            "name": project_name,
            "description": "Test project for group membership",
        }
        project_response = await client.post(
            f"/virtual-labs/{lab_id}/projects",
            json=project_body,
            headers=get_headers(owner_username),
        )

        assert project_response.status_code == HTTPStatus.OK
        project_data = project_response.json()["data"]
        created_project_id = project_data["project"]["id"]

        # get project data to check project admin group
        async with session_context_factory() as session:
            db_project = await session.get(Project, UUID(created_project_id))
            if not db_project:
                pytest.fail("Failed to retrieve created project from DB.")
            proj_admin_group_id = str(db_project.admin_group_id)

        # assert creator is in project admin group
        proj_admins = await gqr.a_retrieve_group_user_ids(proj_admin_group_id)
        assert owner_id in proj_admins

        # assert creator is also in virtual lab member group
        vl_members = await gqr.a_retrieve_group_user_ids(vl_member_group_id)
        assert owner_id in vl_members

        await cleanup_resources(client=client, lab_id=lab_id, user=owner_username)
