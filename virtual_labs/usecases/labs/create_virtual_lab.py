"""Create a virtual lab.

1. External provisioning with a `SagaCompensator` so any later
   failure tears down what was created (Keycloak groups, accounting
   account/discount). Resource UUIDs are pre-allocated and act as
   idempotency seeds so a client retry recovers instead of
   duplicating.
2. A single DB transaction (`async with session.begin():`) bundles
   every local write — vlab row, free subscription, staged Stripe
   customer — so a crash mid-transaction leaves no partial state.
3. Post-commit side effects (Keycloak custom properties,
   welcome email) via `PostCommitActions`. Failures are logged but
   do not roll back the committed vlab.

"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Awaitable, Callable, Literal
from uuid import uuid4

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.infrastructure.email.send_welcome_email import send_welcome_email
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.infrastructure.kc.models import CreatedGroup
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.infrastructure.stripe.types import PostCommitActions
from virtual_labs.services.stripe_customer import StripeCustomerCreationError
from virtual_labs.shared.group_namespace import make_virtual_lab_group_name
from virtual_labs.shared.saga import SagaCompensator
from virtual_labs.usecases import accounting as accounting_cases

GroupRole = Literal["admin_group", "member_group"]
GroupIds = dict[GroupRole, CreatedGroup]


def _welcome_bonus_credits() -> Decimal:
    """Initial balance for a new virtual lab account."""
    return (
        settings.WELCOME_BONUS_CREDITS if settings.ENABLE_WELCOME_BONUS else Decimal(0)
    )


@asynccontextmanager
async def _provision(
    comp: SagaCompensator,
    *,
    name: str,
    message: str,
    error_code: VliErrorCode = VliErrorCode.EXTERNAL_SERVICE_ERROR,
    http_status: HTTPStatus = HTTPStatus.BAD_GATEWAY,
) -> AsyncIterator[None]:
    """Run one external-provisioning step under the saga.

    A single uniform error path:

      * `VliError` raised inside the body passes through unchanged
        (the body already mapped to a typed error), but still triggers
        compensation of every previously-pushed undo.
      * Any other exception logs the underlying cause, compensates,
        and re-raises as a `VliError` shaped for the API surface.
    """
    try:
        yield
    except VliError:
        await comp.compensate(reason=name)
        raise
    except Exception as ex:
        logger.error(f"{name} failed: {ex}")
        await comp.compensate(reason=name)
        raise VliError(
            error_code=error_code,
            http_status_code=http_status,
            message=message,
        ) from ex


async def _ensure_stripe_customer_id(*, user_id: UUID4, email: str, name: str) -> str:
    """Resolve the user's Stripe customer id without any DB activity."""
    customer = await get_stripe_repository().create_customer(
        user_id=user_id,
        email=email,
        name=name,
    )
    if customer is None:
        raise StripeCustomerCreationError(user_id)
    return customer.id


async def _stage_stripe_user_if_missing(
    session: AsyncSession, *, user_id: UUID4, stripe_customer_id: str
) -> None:
    """Insert the local `stripe_user` row inside the caller's txn."""
    existing = await session.scalar(
        select(models.StripeUser).where(models.StripeUser.user_id == user_id)
    )
    if existing is None:
        session.add(
            models.StripeUser(user_id=user_id, stripe_customer_id=stripe_customer_id)
        )
        await session.flush()


async def _update_user_custom_properties(
    user_id: UUID4,
    properties: list[tuple[str, str | None, Literal["multiple", "unique"]]],
) -> None:
    user = await KeycloakRealm.a_get_user(user_id=user_id)
    update_data: dict[str, object] = {
        "email": user.get("email"),
        "firstName": user.get("firstName"),
        "lastName": user.get("lastName"),
    }
    attributes = user.get("attributes", {})
    merged_attributes = {
        key: value if isinstance(value, list) else [str(value)]
        for key, value in attributes.items()
    }

    for field, value, value_type in properties:
        str_value = str(value) if value is not None else ""
        if value_type == "multiple":
            merged_attributes.setdefault(field, []).append(str_value)
        else:
            merged_attributes[field] = [str_value]

    update_data["attributes"] = merged_attributes

    await KeycloakRealm.a_update_user(
        user_id=user_id,
        payload=update_data,
    )


def _map_db_error(err: Exception) -> VliError:
    if isinstance(err, IntegrityError):
        return VliError(
            message="Another virtual lab with same name already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )
    if isinstance(err, SQLAlchemyError):
        return VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    return VliError(
        message="Virtual lab could not be created",
        error_code=VliErrorCode.SERVER_ERROR,
        http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
    )


async def _make_kc_groups_compensation(
    groups: GroupIds,
) -> Callable[[], Awaitable[None]]:
    """Build a saga undo that deletes both Keycloak groups."""

    async def _undo() -> None:
        for created in (groups["admin_group"], groups["member_group"]):
            try:
                await KeycloakRealm.a_delete_group(group_id=created["id"])
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to delete KC group {created['id']}: {exc}")

    return _undo


async def _create_keycloak_groups(lab_id: UUID4, lab_name: str) -> GroupIds:
    try:
        admin_group_name = make_virtual_lab_group_name(lab_id, UserRoleEnum.admin)
        member_group_name = make_virtual_lab_group_name(lab_id, UserRoleEnum.member)
        admin_group, member_group = await asyncio.gather(
            KeycloakRealm.a_create_group(
                {"name": admin_group_name},
            ),
            KeycloakRealm.a_create_group(
                {"name": member_group_name},
            ),
        )
        assert admin_group is not None
        assert member_group is not None
        return {
            "admin_group": {"id": admin_group, "name": admin_group_name},
            "member_group": {"id": member_group, "name": member_group_name},
        }
    except IdentityError:
        raise
    except Exception as error:
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=str(error),
        )


async def _insert_free_subscription(
    session: AsyncSession,
    *,
    user_id: UUID4,
    virtual_lab_id: UUID4,
    status: models.SubscriptionStatus,
) -> None:
    """Stage a FREE subscription row in the current transaction.

    Direct SQLAlchemy instead of going through `SubscriptionRepository`
    because that repo's `create_free_subscription` commits eagerly,
    which would break the outer `async with db.begin():` block.
    """
    tier = (
        await session.execute(
            select(models.SubscriptionTier).where(
                models.SubscriptionTier.tier == models.SubscriptionTierEnum.FREE
            )
        )
    ).scalar_one()

    session.add(
        models.FreeSubscription(
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            tier_id=tier.id,
            subscription_type=models.SubscriptionType.FREE,
            status=status,
            current_period_start=datetime.now(),
            current_period_end=datetime.max,
        )
    )
    await session.flush()


async def _insert_virtual_lab(
    session: AsyncSession,
    *,
    new_lab_id: UUID4,
    owner_id: UUID4,
    owner_email: str,
    admin_group_id: str,
    member_group_id: str,
    payload: domain.VirtualLabCreate,
) -> models.VirtualLab:
    """Stage the VirtualLab row in the current transaction."""
    db_lab = models.VirtualLab(
        id=new_lab_id,
        owner_id=owner_id,
        admin_group_id=admin_group_id,
        member_group_id=member_group_id,
        name=payload.name,
        description=payload.description,
        reference_email=payload.reference_email or owner_email,
        entity=payload.entity,
        compute_cell=payload.compute_cell,
    )
    session.add(db_lab)
    await session.flush()
    await session.refresh(db_lab)
    return db_lab


async def _ensure_virtual_lab_uniqueness(
    session: AsyncSession, *, owner_id: UUID4
) -> None:
    """Enforce the single-vlab-per-user invariant."""
    if owner_id == settings.MULTIPLE_VLABS_ALLOWED_USER_ID:
        return
    existing = await session.scalar(
        select(models.VirtualLab).where(
            models.VirtualLab.owner_id == owner_id,
            ~models.VirtualLab.deleted,
        )
    )
    if existing is not None:
        raise VliError(
            message="User already has a virtual lab",
            error_code=VliErrorCode.FORBIDDEN_OPERATION,
            http_status_code=HTTPStatus.FORBIDDEN,
        )


async def create_virtual_lab(
    db: AsyncSession,
    lab: domain.VirtualLabCreate,
    auth: tuple[AuthUserGrants, str],
) -> domain.VirtualLabDetails:
    owner_id = auth[0].id
    owner_email = auth[0].email
    draft_virtual_lab_id: UUID4 = uuid4()

    # preflight: Keycloak userinfo (no DB activity).
    try:
        kc_user = await KeycloakRealm.a_get_user(user_id=str(owner_id))
    except Exception as error:
        logger.error(f"Preflight reads failed for vlab creation: {error}")
        raise VliError(
            message="Could not load user context",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    # external provisioning. Each step is wrapped by the
    # `_provision` context manager which compensates the saga and
    # maps unexpected errors to a typed `VliError`
    comp = SagaCompensator()

    async with _provision(
        comp,
        name="keycloak groups",
        message="Keycloak group setup failed",
    ):
        try:
            groups = await _create_keycloak_groups(draft_virtual_lab_id, lab.name)
            comp.push(await _make_kc_groups_compensation(groups))
            await KeycloakRealm.a_group_user_add(
                user_id=owner_id, group_id=groups["admin_group"]["id"]
            )
        except ValueError as error:
            raise VliError(
                message=str(error),
                error_code=VliErrorCode.INVALID_REQUEST,
                http_status_code=HTTPStatus.BAD_REQUEST,
            )
        except IdentityError:
            raise VliError(
                message=f"User {owner_id} is not authorized to create virtual lab",
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=HTTPStatus.FORBIDDEN,
            )

    if settings.ACCOUNTING_BASE_URL is not None:
        async with _provision(
            comp,
            name="accounting account",
            message="Virtual lab account creation failed",
        ):
            await accounting_cases.create_virtual_lab_account(
                virtual_lab_id=draft_virtual_lab_id,
                name=lab.name,
                balance=_welcome_bonus_credits(),
            )
            comp.push(_log_orphan_accounting_account(draft_virtual_lab_id))

    async with _provision(
        comp,
        name="stripe customer",
        message="Payment-provider setup failed",
    ):
        stripe_customer_id = await _ensure_stripe_customer_id(
            user_id=owner_id,
            email=kc_user.get("email", owner_email),
            name=f"{kc_user.get('firstName', '')} {kc_user.get('lastName', '')}",
        )

    deferred = PostCommitActions()
    virtual_lab_draft: domain.VirtualLabDetails

    try:
        async with db.begin():
            await _ensure_virtual_lab_uniqueness(db, owner_id=owner_id)
            await _stage_stripe_user_if_missing(
                db, user_id=owner_id, stripe_customer_id=stripe_customer_id
            )
            db_lab = await _insert_virtual_lab(
                db,
                new_lab_id=draft_virtual_lab_id,
                owner_id=owner_id,
                owner_email=owner_email,
                admin_group_id=groups["admin_group"]["id"],
                member_group_id=groups["member_group"]["id"],
                payload=lab,
            )
            # Snapshot before commit so we never touch the ORM object
            virtual_lab_draft = domain.VirtualLabDetails.model_validate(db_lab)

            await _insert_free_subscription(
                db,
                user_id=owner_id,
                virtual_lab_id=draft_virtual_lab_id,
                status=models.SubscriptionStatus.ACTIVE,
            )
    except (IntegrityError, SQLAlchemyError) as err:
        await comp.compensate(reason="database error")
        logger.error(f"Virtual lab DB write failed: {err}")
        raise _map_db_error(err)
    except VliError:
        await comp.compensate(reason="VLI error during DB phase")
        raise
    except Exception as err:  # noqa: BLE001
        await comp.compensate(reason="unknown error during DB phase")
        logger.exception(f"Unexpected failure while creating virtual lab: {err}")
        raise _map_db_error(err)

    # post-commit side effects
    tier_mode = models.SubscriptionTierEnum.FREE.value

    async def _update_kc_props() -> None:
        await _update_user_custom_properties(
            user_id=owner_id,
            properties=[
                ("plan", tier_mode, "multiple"),
                ("virtual_lab_id", str(virtual_lab_draft.id), "multiple"),
            ],
        )

    deferred.add(_update_kc_props)

    if kc_user.get("email", owner_email):

        async def _welcome() -> None:
            await send_welcome_email(owner_email)

        deferred.add(_welcome)

    await deferred.run()

    return virtual_lab_draft


async def create_course_vlab(
    db: AsyncSession,
    lab: domain.VirtualLabCreate,
    auth: tuple[AuthUserGrants, str],
) -> domain.VirtualLabDetails:
    user_id = auth[0].id
    user_email = auth[0].email
    draft_course_id: UUID4 = uuid4()

    # external provisioning. No DB activity
    comp = SagaCompensator()

    async with _provision(
        comp,
        name="keycloak groups",
        message="Keycloak group setup failed",
    ):
        try:
            groups = await _create_keycloak_groups(draft_course_id, lab.name)
            comp.push(await _make_kc_groups_compensation(groups))
            await KeycloakRealm.a_group_user_add(
                user_id=user_id,
                group_id=groups["admin_group"]["id"],
            )
        except IdentityError:
            raise VliError(
                message=f"User {user_id} is not authorized to create virtual lab",
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=HTTPStatus.FORBIDDEN,
            )

    if settings.ACCOUNTING_BASE_URL is not None:
        async with _provision(
            comp,
            name="accounting account",
            message="Virtual lab account creation failed",
        ):
            await accounting_cases.create_virtual_lab_account(
                virtual_lab_id=draft_course_id,
                name=lab.name,
                balance=Decimal(0),
            )
            comp.push(_log_orphan_accounting_account(draft_course_id))

    try:
        async with db.begin():
            db_lab = await _insert_virtual_lab(
                db,
                new_lab_id=draft_course_id,
                owner_id=user_id,
                owner_email=user_email,
                admin_group_id=groups["admin_group"]["id"],
                member_group_id=groups["member_group"]["id"],
                payload=lab,
            )
            lab_details = domain.VirtualLabDetails.model_validate(db_lab)
    except (IntegrityError, SQLAlchemyError) as err:
        await comp.compensate(reason="database error")
        logger.error(f"Course vlab DB write failed: {err}")
        raise _map_db_error(err)
    except Exception as err:  # noqa: BLE001
        await comp.compensate(reason="unknown error during DB phase")
        logger.exception(f"Unexpected failure while creating course vlab: {err}")
        raise _map_db_error(err)

    return lab_details


def _log_orphan_accounting_account(
    virtual_lab_id: UUID4,
) -> Callable[[], Awaitable[None]]:
    """Placeholder compensation for accounting account creation.

    The accounting service does not currently expose a delete-account
    endpoint, so the safest behavior is to log the orphan so an
    operator can reconcile. This keeps the saga shape uniform, when
    a real deletion endpoint lands, this function is the single place
    to swap in the actual undo call.
    """

    async def _undo() -> None:
        logger.warning(
            f"Orphan accounting account left for vlab {virtual_lab_id}; "
            "no delete endpoint available — reconcile manually."
        )

    return _undo
