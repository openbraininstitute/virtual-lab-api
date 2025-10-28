import asyncio
import time
import typing
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import AsyncGenerator, Awaitable, cast
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from loguru import logger
from requests import get
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import SetupIntent

from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.infrastructure.db.models import (
    Bookmark,
    FreeSubscription,
    Notebook,
    PaidSubscription,
    PaymentMethod,
    Project,
    ProjectInvite,
    ProjectStar,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
    SubscriptionType,
    UserPreference,
    VirtualLab,
    VirtualLabInvite,
)
from virtual_labs.infrastructure.kc.auth import get_client_token
from virtual_labs.infrastructure.kc.config import kc_auth
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.repositories.group_repo import GroupMutationRepository

email_server_baseurl = "http://localhost:8025"


@asynccontextmanager
async def session_context_factory() -> AsyncGenerator[AsyncSession, None]:
    async with session_pool.session() as session:
        yield session


def auth(username: str = "test") -> str:
    token = kc_auth.token(username=username, password="test")
    return cast(str, token["access_token"])


def get_headers(username: str = "test") -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {auth(username)}",
    }


def get_client_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"bearer {get_client_token()}",
    }


async def create_mock_lab(
    client: AsyncClient, owner_username: str = "test"
) -> Response:
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
        "email_status": "verified",
    }
    headers = get_headers(owner_username)

    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    assert response.status_code == 200
    return response


async def create_mock_lab_with_project(
    client: AsyncClient, owner_username: str = "test"
) -> tuple[dict[str, str], str]:
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers(owner_username)
    lab_response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )
    assert lab_response.status_code == 200
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    project_body = {
        "name": f"Test Project {uuid4()}",
        "description": "Test",
    }
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects",
        json=project_body,
        headers=headers,
    )

    project_id = project_response.json()["data"]["project"]["id"]
    return (lab_response.json()["data"]["virtual_lab"], project_id)


def get_invite_token_from_email_body(email_body: str) -> str:
    return email_body.split("token=")[1].split('" ')[0]


def get_invite_token_from_email(recipient_email: str) -> str:
    email_body = get(
        f"{email_server_baseurl}/view/latest.html?query=to:{recipient_email}"
    ).text

    encoded_invite_token = get_invite_token_from_email_body(email_body)
    return encoded_invite_token


async def cleanup_resources(
    client: AsyncClient, lab_id: str, user: str | None = None
) -> None:
    """Performs cleanup of following resources for lab_id:
    1. Delete all payments and subscriptions linked to this virtual lab
    2. Deprecates underlying nexus org/project by calling the DELETE endpoints
    3. Deletes lab/project row along with lab_invite, project_invite, project_star, bookmarks, rows from the DB
    4. Deletes admin and member groups from keycloak
    """
    # 1. Delete payments and subscriptions
    async with session_context_factory() as session:
        await session.execute(
            statement=delete(SubscriptionPayment).where(
                SubscriptionPayment.subscription_id.in_(
                    select(Subscription.id).where(
                        Subscription.virtual_lab_id == UUID(lab_id)
                    )
                )
            )
        )
        await session.execute(
            statement=delete(FreeSubscription).where(
                FreeSubscription.virtual_lab_id == UUID(lab_id)
            )
        )
        await session.execute(
            statement=delete(PaidSubscription).where(
                PaidSubscription.virtual_lab_id == UUID(lab_id)
            )
        )
        await session.execute(
            statement=delete(Subscription).where(
                Subscription.virtual_lab_id == UUID(lab_id)
            )
        )
        await session.commit()

    project_ids = []
    async with session_context_factory() as session:
        stmt = select(Project.id).filter(Project.virtual_lab_id == UUID(lab_id))
        all = (await session.execute(statement=stmt)).scalars().all()
        project_ids = [str(project_id) for project_id in all]
    # 2. Call DELETE endpoints (which will deprecate nexus resources)
    for project_id in project_ids:
        try:
            project_delete_response = await client.delete(
                f"/virtual-labs/{lab_id}/projects/{project_id}",
                headers=get_headers(user if user else "test"),
            )
        except Exception:
            assert (
                project_delete_response.status_code == HTTPStatus.BAD_REQUEST
            )  # TODO: The response code for deleting already deleted lab and project should be the same.
    try:
        lab_delete_response = await client.delete(
            f"/virtual-labs/{lab_id}", headers=get_headers(user if user else "test")
        )
    except Exception:
        assert lab_delete_response.status_code == HTTPStatus.NOT_FOUND

    # 3. Delete database rows
    project_group_ids: list[tuple[str, str]] = []
    async with session_context_factory() as session:
        for project_id in project_ids:
            await session.execute(
                delete(UserPreference).where(UserPreference.project_id == project_id)
            )

        for project_id in project_ids:
            await session.execute(
                statement=delete(ProjectInvite).where(
                    ProjectInvite.project_id == project_id
                )
            )

            await session.execute(
                statement=delete(ProjectStar).where(
                    ProjectStar.project_id == project_id
                )
            )

            await session.execute(
                statement=delete(Bookmark).where(Bookmark.project_id == project_id)
            )

            await session.execute(
                statement=delete(Notebook).where(Notebook.project_id == project_id)
            )

            logger.debug(f"Deleting project {project_id}")
            project_data = (
                await session.execute(
                    statement=delete(Project)
                    .where(Project.id == project_id)
                    .returning(Project.admin_group_id, Project.member_group_id)
                )
            ).first()

            if project_data is not None:
                project_group_ids.append(project_data._tuple())

        await session.execute(
            statement=delete(VirtualLabInvite).where(
                VirtualLabInvite.virtual_lab_id == lab_id
            )
        )

        await session.execute(
            statement=delete(PaymentMethod).where(
                PaymentMethod.virtual_lab_id == lab_id
            )
        )

        lab_data = (
            await session.execute(
                statement=delete(VirtualLab)
                .where(VirtualLab.id == lab_id)
                .returning(
                    VirtualLab.admin_group_id,
                    VirtualLab.member_group_id,
                )
            )
        ).one()

        await session.commit()

    # 4. Delete KC groups
    group_repo = GroupMutationRepository()
    for project_group_id in project_group_ids:
        group_repo.delete_group(group_id=project_group_id[0])
        group_repo.delete_group(group_id=project_group_id[1])
    group_repo.delete_group(group_id=lab_data[0])
    group_repo.delete_group(group_id=lab_data[1])


async def create_confirmed_setup_intent(customer_id: str) -> SetupIntent:
    setup_intent = await stripe_client.setup_intents.create_async(
        {"customer": customer_id}
    )
    setup_intent_confirmed = await stripe_client.setup_intents.confirm_async(
        setup_intent.id,
        {
            "return_url": "http://localhost:4000",
            "payment_method": "pm_card_visa",
        },
    )
    intent = await stripe_client.setup_intents.retrieve_async(
        setup_intent_confirmed.id, {"expand": ["payment_method"]}
    )

    return intent


async def wait_until(
    somepredicate: typing.Callable[..., Awaitable[bool]],
    timeout: int,
    period: float = 0.25,
    *args: typing.Any,
    **kwargs: typing.Any,
) -> bool:
    mustend = time.time() + timeout
    while time.time() < mustend:
        if await somepredicate(*args, **kwargs):
            return True
        await asyncio.sleep(period)
    return False


async def create_paid_subscription_for_user(user_id: UUID) -> None:
    """
    create a paid subscription for a user to enable inviting others.
    """
    async with session_context_factory() as session:
        # Create a paid subscription for the user
        now = datetime.now()
        subscription = PaidSubscription(
            id=uuid4(),
            user_id=user_id,
            tier_id="00000000-0000-0000-0000-000000000002",
            stripe_subscription_id="sub_xxxx",
            customer_id="cus_xxxx",
            stripe_price_id="price_xxxx",
            status=SubscriptionStatus.ACTIVE,
            amount=400,
            interval="month",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            subscription_type=SubscriptionType.PRO,
            created_at=now,
            updated_at=now,
        )
        session.add(subscription)
        await session.commit()
        logger.info(f"Created paid subscription for user {user_id}")


async def create_free_subscription_for_user(user_id: UUID) -> None:
    """
    create a free subscription for a user.
    """
    async with session_context_factory() as session:
        # Create a free subscription for the user
        now = datetime.utcnow()
        subscription = FreeSubscription(
            id=uuid4(),
            user_id=user_id,
            tier_id="00000000-0000-0000-0000-000000000001",
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            subscription_type=SubscriptionType.FREE,
            created_at=now,
            updated_at=now,
        )
        session.add(subscription)
        await session.commit()
        logger.info(f"Created free subscription for user {user_id}")


async def get_user_id_from_test_auth(auth_header: str) -> UUID:
    auth_user = await kc_auth.a_decode_token(
        token=auth_header.replace("Bearer ", ""), validate=False
    )
    return UUID(auth_user["sub"])
