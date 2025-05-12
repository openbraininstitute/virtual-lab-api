import asyncio
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import AsyncGenerator, Dict, Tuple
from uuid import UUID, uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.db.models import (
    VirtualLab,
    VirtualLabInvite,
)
from virtual_labs.infrastructure.email.email_utils import InviteOrigin
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
    get_headers,
    get_invite_token_from_email,
    session_context_factory,
)

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


# Helper to generate invite tokens manually
def generate_test_invite_token(
    invite_id: UUID,
    origin: InviteOrigin = InviteOrigin.LAB,
    expires_delta: timedelta | None = None,
    secret_key: str = settings.INVITE_JWT_SECRET,
    algorithm: str = "HS256",
) -> str:
    """Generates a JWT token for testing purposes."""
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.INVITE_EXPIRES_IN_DAYS)

    to_encode = {
        "invite_id": str(invite_id),
        "exp": expire,
        "origin": origin.value,
    }
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    return encoded_jwt


# Helper to check Keycloak group membership
async def check_user_group_membership(
    user_id: str, group_id: str, should_be_member: bool
) -> None:
    """Checks if a user is a member of a specific Keycloak group."""
    gqr = GroupQueryRepository()
    try:
        members = await gqr.a_retrieve_group_user_ids(group_id=group_id)
        is_member = user_id in members
        assert is_member == should_be_member
    except Exception as e:
        pytest.fail(
            f"Failed to check group membership for user {user_id} in group {group_id}: {e}"
        )


# Main setup fixture for lab creation and user invites
@pytest_asyncio.fixture
async def setup_lab_and_invite(
    async_test_client: AsyncClient, test_user_ids: Dict[str, str]
) -> AsyncGenerator[
    Tuple[AsyncClient, str, VirtualLab, Dict[str, str], str, UUID], None
]:
    """
    Sets up a Virtual Lab, invites a user, and yields necessary info.
    Cleans up resources afterwards.
    """
    lab_response = await create_mock_lab(async_test_client, owner_username="test")
    lab_id_str = lab_response.json()["data"]["virtual_lab"]["id"]
    lab_id_uuid = UUID(lab_id_str)

    invitee_email = "test-2@test.com"
    invitee_role = UserRoleEnum.admin

    headers = get_headers("test")

    db_lab = None

    async with session_context_factory() as session:
        db_lab = await session.get(VirtualLab, lab_id_uuid)
        if not db_lab:
            pytest.fail(f"Failed to retrieve created lab {lab_id_uuid} from DB.")

    # Invite the user
    invite_payload = {"email": invitee_email, "role": invitee_role.value}
    invite_response = await async_test_client.post(
        f"/virtual-labs/{lab_id_str}/invites", headers=headers, json=invite_payload
    )
    assert invite_response.status_code == HTTPStatus.OK
    invite_id_str = invite_response.json()["data"]["invite_id"]
    invite_id_uuid = UUID(invite_id_str)

    await asyncio.sleep(1)
    invite_token = get_invite_token_from_email(recipient_email=invitee_email)
    assert invite_token is not None

    assert db_lab is not None
    yield (
        async_test_client,
        lab_id_str,
        db_lab,
        test_user_ids,
        invite_token,
        invite_id_uuid,
    )

    await cleanup_resources(client=async_test_client, lab_id=lab_id_str)


@pytest.mark.integration
async def test_accept_admin_invite_success(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """
    Tests successfully accepting an admin invite.
    Verifies user is added to the correct Keycloak group and removed from the other.
    """
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        invite_token,
        invite_id,
    ) = setup_lab_and_invite

    invitee_username = "test-2"
    invitee_id = user_ids[invitee_username]
    admin_group_id = str(db_lab.admin_group_id)
    member_group_id = str(db_lab.member_group_id)

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={invite_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["status"] == "accepted"
    assert data["origin"] == InviteOrigin.LAB.value
    assert data["invite_id"] == str(invite_id)
    assert data["virtual_lab_id"] == lab_id

    async with session_context_factory() as session:
        db_invite = await session.get(VirtualLabInvite, invite_id)
        assert db_invite is not None
        assert db_invite.accepted is True

    await check_user_group_membership(invitee_id, admin_group_id, should_be_member=True)
    await check_user_group_membership(
        invitee_id, member_group_id, should_be_member=False
    )


@pytest.mark.integration
async def test_accept_member_invite_success(
    async_test_client: AsyncClient, test_user_ids: Dict[str, str]
) -> None:
    """
    Tests successfully accepting a member invite.
    Verifies user is added to the correct Keycloak group.
    """
    client = async_test_client
    lab_owner_username = "test"

    invitee_username = "test-3"
    invitee_email = "test-3@test.com"
    invitee_id = test_user_ids[invitee_username]
    invitee_role = UserRoleEnum.member

    lab_response = await create_mock_lab(client, owner_username=lab_owner_username)
    lab_id_str = lab_response.json()["data"]["virtual_lab"]["id"]
    lab_id_uuid = UUID(lab_id_str)

    admin_group_id = ""
    member_group_id = ""
    # Retrieve lab details
    async with session_context_factory() as session:
        db_lab = await session.get(VirtualLab, lab_id_uuid)
        if not db_lab:
            pytest.fail(f"Failed to retrieve created lab {lab_id_uuid} from DB.")
        admin_group_id = str(db_lab.admin_group_id)
        member_group_id = str(db_lab.member_group_id)

    # Invite the user as member
    invite_payload = {"email": invitee_email, "role": invitee_role.value}
    invite_headers = get_headers(lab_owner_username)
    invite_response = await client.post(
        f"/virtual-labs/{lab_id_str}/invites",
        headers=invite_headers,
        json=invite_payload,
    )
    assert invite_response.status_code == HTTPStatus.OK
    invite_id_str = invite_response.json()["data"]["invite_id"]
    invite_id_uuid = UUID(invite_id_str)

    await asyncio.sleep(1)
    invite_token = get_invite_token_from_email(recipient_email=invitee_email)
    assert invite_token is not None

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={invite_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    assert data["status"] == "accepted"
    assert data["invite_id"] == invite_id_str

    async with session_context_factory() as session:
        db_invite = await session.get(VirtualLabInvite, invite_id_uuid)
        assert db_invite is not None
        assert db_invite.accepted is True

    await check_user_group_membership(
        invitee_id, member_group_id, should_be_member=True
    )
    await check_user_group_membership(
        invitee_id, admin_group_id, should_be_member=False
    )

    await cleanup_resources(client=client, lab_id=lab_id_str)


@pytest.mark.integration
async def test_accept_already_accepted_invite(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """
    Tests attempting to accept an invite that has already been accepted.
    """
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        invite_token,
        invite_id,
    ) = setup_lab_and_invite
    invitee_username = "test-2"
    invitee_id = user_ids[invitee_username]
    admin_group_id = str(db_lab.admin_group_id)
    member_group_id = str(db_lab.member_group_id)

    accept_headers = get_headers(username=invitee_username)
    first_response = await client.post(
        f"/invites?token={invite_token}", headers=accept_headers
    )
    assert first_response.status_code == HTTPStatus.OK
    assert first_response.json()["data"]["status"] == "accepted"

    await check_user_group_membership(invitee_id, admin_group_id, should_be_member=True)
    await check_user_group_membership(
        invitee_id, member_group_id, should_be_member=False
    )

    second_response = await client.post(
        f"/invites?token={invite_token}", headers=accept_headers
    )

    assert second_response.status_code == HTTPStatus.OK
    data = second_response.json()["data"]
    assert data["status"] == "already_accepted"
    assert data["invite_id"] == str(invite_id)
    assert data["virtual_lab_id"] == lab_id

    await check_user_group_membership(invitee_id, admin_group_id, should_be_member=True)
    await check_user_group_membership(
        invitee_id, member_group_id, should_be_member=False
    )


@pytest.mark.integration
async def test_accept_expired_invite(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """Tests attempting to accept an invite using an expired token."""
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        _,
        invite_id,
    ) = setup_lab_and_invite
    invitee_username = "test-2"

    expired_token = generate_test_invite_token(
        invite_id=invite_id, expires_delta=timedelta(seconds=-1)
    )

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={expired_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    error_data = response.json()
    assert error_data["error_code"] == "TOKEN_EXPIRED"
    assert "Invite Token is not valid" in error_data["message"]
    assert "Invitation is expired" in error_data["details"]


@pytest.mark.integration
async def test_accept_invalid_signature_invite(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """Tests attempting to accept an invite using a token with an invalid signature."""
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        _,
        invite_id,
    ) = setup_lab_and_invite
    invitee_username = "test-2"

    invalid_sig_token = generate_test_invite_token(
        invite_id=invite_id, secret_key="this is the wrong secret key"
    )

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={invalid_sig_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    error_data = response.json()
    assert error_data["error_code"] == "INVALID_PARAMETER"
    assert "Invite Token is not valid" in error_data["message"]
    assert "malformed" in error_data["details"]


@pytest.mark.integration
async def test_accept_malformed_token_invite(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """Tests attempting to accept an invite using a malformed token string."""
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        _,
        invite_id,
    ) = setup_lab_and_invite
    invitee_username = "test-2"
    malformed_token = "this.is.not.a.jwt.token"

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={malformed_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    error_data = response.json()
    assert error_data["error_code"] == "INVALID_PARAMETER"
    assert "Invite Token is not valid" in error_data["message"]
    assert "malformed" in error_data["details"]


@pytest.mark.integration
async def test_accept_non_existent_invite(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """Tests attempting to accept an invite using a token for a non-existent invite ID."""
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        _,
        invite_id,
    ) = setup_lab_and_invite
    invitee_username = "test-2"
    non_existent_invite_id = uuid4()

    non_existent_token = generate_test_invite_token(invite_id=non_existent_invite_id)

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={non_existent_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    error_data = response.json()
    assert error_data["error_code"] == "INVALID_REQUEST"
    assert "No invite was found" in error_data["message"]


@pytest.mark.integration
async def test_accept_deleted_invite(
    setup_lab_and_invite: Tuple[
        AsyncClient, str, VirtualLab, Dict[str, str], str, UUID
    ],
) -> None:
    """Tests attempting to accept an invite that has been deleted from the database."""
    (
        client,
        lab_id,
        db_lab,
        user_ids,
        invite_token,
        invite_id,
    ) = setup_lab_and_invite
    invitee_username = "test-2"

    async with session_context_factory() as session:
        stmt = delete(VirtualLabInvite).where(VirtualLabInvite.id == invite_id)
        await session.execute(stmt)
        await session.commit()

        check_invite = await session.get(VirtualLabInvite, invite_id)
        assert check_invite is None

    accept_headers = get_headers(username=invitee_username)
    response = await client.post(
        f"/invites?token={invite_token}", headers=accept_headers
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    error_data = response.json()
    assert error_data["error_code"] == "INVALID_REQUEST"
    assert "No invite was found" in error_data["message"]


@pytest.mark.integration
async def test_accept_invite_role_change_before_accept(
    async_test_client: AsyncClient, test_user_ids: Dict[str, str]
) -> None:
    """
    Tests scenario where user receives multiple invites with different roles
    before accepting any. Acceptance of the *last* invite should dictate the role.
    """
    client = async_test_client
    lab_owner_username = "test"

    invitee_username = "test-4"
    invitee_email = "test-4@test.com"
    invitee_id = test_user_ids[invitee_username]

    lab_response = await create_mock_lab(client, owner_username=lab_owner_username)
    lab_id_str = lab_response.json()["data"]["virtual_lab"]["id"]
    lab_id_uuid = UUID(lab_id_str)
    invite_headers = get_headers(lab_owner_username)

    admin_group_id = ""
    member_group_id = ""

    async with session_context_factory() as session:
        db_lab = await session.get(VirtualLab, lab_id_uuid)
        if not db_lab:
            pytest.fail(f"Failed to retrieve created lab {lab_id_uuid} from DB.")
        admin_group_id = str(db_lab.admin_group_id)
        member_group_id = str(db_lab.member_group_id)

    # 1. Invite user as ADMIN
    admin_invite_payload = {"email": invitee_email, "role": UserRoleEnum.admin.value}
    admin_invite_response = await client.post(
        f"/virtual-labs/{lab_id_str}/invites",
        headers=invite_headers,
        json=admin_invite_payload,
    )
    assert admin_invite_response.status_code == HTTPStatus.OK
    admin_invite_id_str = admin_invite_response.json()["data"]["invite_id"]

    await asyncio.sleep(1)
    admin_invite_token = get_invite_token_from_email(recipient_email=invitee_email)

    assert admin_invite_token is not None

    # 2. Invite SAME user as MEMBER (updates existing DB invite record's role)
    member_invite_payload = {"email": invitee_email, "role": UserRoleEnum.member.value}
    member_invite_response = await client.post(
        f"/virtual-labs/{lab_id_str}/invites",
        headers=invite_headers,
        json=member_invite_payload,
    )
    assert member_invite_response.status_code == HTTPStatus.OK
    member_invite_id_str = member_invite_response.json()["data"]["invite_id"]

    assert admin_invite_id_str != member_invite_id_str
    await asyncio.sleep(1)
    member_invite_token = get_invite_token_from_email(recipient_email=invitee_email)

    assert member_invite_token is not None
    assert admin_invite_token != member_invite_token

    invite_id_uuid = UUID(member_invite_id_str)

    # 3. Accept the MEMBER invite (the most recent one)
    accept_headers = get_headers(username=invitee_username)
    accept_response = await client.post(
        f"/invites?token={member_invite_token}", headers=accept_headers
    )

    assert accept_response.status_code == HTTPStatus.OK
    data = accept_response.json()["data"]
    assert data["status"] == "accepted"
    assert data["invite_id"] == member_invite_id_str

    await check_user_group_membership(
        invitee_id, member_group_id, should_be_member=True
    )
    await check_user_group_membership(
        invitee_id, admin_group_id, should_be_member=False
    )

    async with session_context_factory() as session:
        db_invite = await session.get(VirtualLabInvite, invite_id_uuid)
        assert db_invite is not None
        assert db_invite.accepted is True
        assert db_invite.role == UserRoleEnum.member.value

    accept_admin_again_response = await client.post(
        f"/invites?token={admin_invite_token}", headers=accept_headers
    )
    assert accept_admin_again_response.status_code == HTTPStatus.OK
    data_admin_again = accept_admin_again_response.json()["data"]
    assert data_admin_again["status"] == "accepted"
    assert data_admin_again["invite_id"] == admin_invite_id_str

    await check_user_group_membership(
        invitee_id, member_group_id, should_be_member=False
    )
    await check_user_group_membership(
        invitee_id,
        admin_group_id,
        should_be_member=True,
    )

    await cleanup_resources(client=client, lab_id=lab_id_str)


@pytest.mark.integration
async def test_accept_multiple_invites_different_emails_same_user(
    async_test_client: AsyncClient, test_user_ids: Dict[str, str]
) -> None:
    """
    Tests scenario where two different emails are invited (admin, member),
    but the same user accepts both sequentially. The user should end up
    only in the group corresponding to the *last accepted* invite's role.
    """
    client = async_test_client
    lab_owner_username = "test"

    # Emails to invite
    invitee_email_admin = "first-email-of-user@test.org"
    invitee_email_member = "another-email-for-the-user@test.org"

    # The single user who will accept both invites
    accepting_user_username = "test-4"
    accepting_user_id = test_user_ids[accepting_user_username]

    lab_response = await create_mock_lab(client, owner_username=lab_owner_username)
    lab_id_str = lab_response.json()["data"]["virtual_lab"]["id"]
    lab_id_uuid = UUID(lab_id_str)
    invite_headers = get_headers(lab_owner_username)

    admin_group_id = ""
    member_group_id = ""

    async with session_context_factory() as session:
        db_lab = await session.get(VirtualLab, lab_id_uuid)
        if not db_lab:
            pytest.fail(f"Failed to retrieve created lab {lab_id_uuid} from DB.")
        admin_group_id = str(db_lab.admin_group_id)
        member_group_id = str(db_lab.member_group_id)

    # 1. Invite email_A as ADMIN
    admin_invite_payload = {
        "email": invitee_email_admin,
        "role": UserRoleEnum.admin.value,
    }
    admin_invite_response = await client.post(
        f"/virtual-labs/{lab_id_str}/invites",
        headers=invite_headers,
        json=admin_invite_payload,
    )
    assert admin_invite_response.status_code == HTTPStatus.OK
    admin_invite_id_str = admin_invite_response.json()["data"]["invite_id"]
    admin_invite_id_uuid = UUID(admin_invite_id_str)
    await asyncio.sleep(1)
    admin_invite_token = get_invite_token_from_email(
        recipient_email=invitee_email_admin
    )
    assert admin_invite_token is not None

    # 2. Invite email_B as MEMBER
    member_invite_payload = {
        "email": invitee_email_member,
        "role": UserRoleEnum.member.value,
    }
    member_invite_response = await client.post(
        f"/virtual-labs/{lab_id_str}/invites",
        headers=invite_headers,
        json=member_invite_payload,
    )
    assert member_invite_response.status_code == HTTPStatus.OK
    member_invite_id_str = member_invite_response.json()["data"]["invite_id"]
    member_invite_id_uuid = UUID(member_invite_id_str)
    await asyncio.sleep(1)
    member_invite_token = get_invite_token_from_email(
        recipient_email=invitee_email_member
    )
    assert member_invite_token is not None

    # Ensure the invite IDs are different
    assert admin_invite_id_uuid != member_invite_id_uuid

    # 3. User 'test-4' accepts the ADMIN invite (for email_A)
    accept_headers = get_headers(username=accepting_user_username)

    accept_admin_response = await client.post(
        f"/invites?token={admin_invite_token}", headers=accept_headers
    )
    assert accept_admin_response.status_code == HTTPStatus.OK
    accept_admin_data = accept_admin_response.json()["data"]
    assert accept_admin_data["status"] == "accepted"
    assert accept_admin_data["invite_id"] == admin_invite_id_str

    # Verify state after first acceptance: user is ADMIN
    await check_user_group_membership(
        accepting_user_id, admin_group_id, should_be_member=True
    )
    await check_user_group_membership(
        accepting_user_id, member_group_id, should_be_member=False
    )
    async with session_context_factory() as session:
        invite_a = await session.get(VirtualLabInvite, admin_invite_id_uuid)
        assert invite_a is not None
        assert invite_a.accepted is True
        assert invite_a.user_id == UUID(accepting_user_id)

    # 4. SAME User 'test-4' accepts the MEMBER invite (for email_B)
    accept_member_response = await client.post(
        f"/invites?token={member_invite_token}", headers=accept_headers
    )
    assert accept_member_response.status_code == HTTPStatus.OK
    accept_member_data = accept_member_response.json()["data"]
    assert accept_member_data["status"] == "accepted"
    assert accept_member_data["invite_id"] == member_invite_id_str

    # Verify state after second acceptance: user should NOW be MEMBER, NOT ADMIN
    await check_user_group_membership(
        accepting_user_id, member_group_id, should_be_member=True
    )
    await check_user_group_membership(
        accepting_user_id, admin_group_id, should_be_member=False
    )
    async with session_context_factory() as session:
        invite_b = await session.get(VirtualLabInvite, member_invite_id_uuid)
        assert invite_b is not None
        assert invite_b.accepted is True
        assert invite_b.user_id == UUID(accepting_user_id)

        invite_a_check = await session.get(VirtualLabInvite, admin_invite_id_uuid)
        assert invite_a_check is not None
        assert invite_a_check.accepted is True
        assert invite_a_check.user_id == UUID(accepting_user_id)

    await cleanup_resources(client=client, lab_id=lab_id_str)
