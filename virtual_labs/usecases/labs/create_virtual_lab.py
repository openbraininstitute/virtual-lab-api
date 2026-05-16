"""Create a virtual lab.

five phases, each one a single `async with` or `await`:

  1. preflight       — read-only Keycloak userinfo
  2. pre-checks      — read-only DB: owner uniqueness + name availability,
                       run before any external work to fail-fast
  3. provisioning    — Keycloak groups + membership, accounting account,
                       Stripe customer, recorded onto a `Ledger` so any
                       later failure unwinds them in LIFO order
  4. persistence     — single DB transaction bundles every local write
                       (stripe_user, vlab, free subscription)
  5. post-commit     — best-effort side effects (KC custom properties,
                       welcome email); failures never roll back the txn

The regular lab vs course lab differences (welcome bonus, owner uniqueness,
post-commit actions) are encoded in `VirtualLabCreationPolicy`; the
orchestrator is identical for both.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.core.ledger import (
    Ledger,
    ledger_container,
    provision,
    transactional_persistence,
)
from virtual_labs.core.ledger.modules.virtual_lab import (
    REGULAR_LAB_POLICY,
    AccountingAccountProvisioningError,
    KeycloakGroupMembershipError,
    KeycloakGroupProvisioningError,
    OwnerAlreadyHasVirtualLabError,
    StripeCustomerProvisioningError,
    UserContextLoadError,
    UserNotAuthorizedToCreateVirtualLabError,
    VirtualLabCreationPolicy,
    VirtualLabNameAlreadyExistsError,
    VirtualLabNameConflictError,
    VirtualLabPersistenceError,
    translate_domain_errors,
)
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
from virtual_labs.repositories import labs as labs_repo
from virtual_labs.services.stripe_customer import StripeCustomerCreationError
from virtual_labs.shared.group_namespace import make_virtual_lab_group_name
from virtual_labs.usecases import accounting as accounting_cases

GroupRole = Literal["admin_group", "member_group"]
GroupIds = dict[GroupRole, CreatedGroup]


# preflight
async def _load_kc_user(owner_id: UUID4) -> dict[str, object]:
    try:
        kc_user: dict[str, object] = await KeycloakRealm.a_get_user(
            user_id=str(owner_id)
        )
        return kc_user
    except Exception as error:
        logger.error(f"Preflight Keycloak userinfo failed: {error}")
        raise UserContextLoadError(owner_id=str(owner_id)) from error


# pre-checks (DB read-only)
async def _ensure_owner_has_no_virtual_lab(
    session: AsyncSession, owner_id: UUID4
) -> None:
    """Enforce the single-vlab-per-user invariant before any external work."""
    if owner_id == settings.MULTIPLE_VLABS_ALLOWED_USER_ID:
        return
    existing = await session.scalar(
        select(models.VirtualLab).where(
            models.VirtualLab.owner_id == owner_id,
            models.VirtualLab.deleted.is_(False),
        )
    )
    if existing is not None:
        raise OwnerAlreadyHasVirtualLabError(owner_id=str(owner_id))


async def _ensure_name_available(session: AsyncSession, name: str) -> None:
    if not name:
        return
    count = await labs_repo.count_virtual_labs_with_name(session, name)
    if count > 0:
        raise VirtualLabNameAlreadyExistsError(name=name)


# external provisioning (ledger-backed)


async def _make_kc_groups_compensation(
    groups: GroupIds,
) -> Callable[[], Awaitable[None]]:
    async def _undo() -> None:
        for created in (groups["admin_group"], groups["member_group"]):
            try:
                await KeycloakRealm.a_delete_group(group_id=created["id"])
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to delete KC group {created['id']}: {exc}")

    return _undo


async def _create_keycloak_groups(lab_id: UUID4, lab_name: str) -> GroupIds:
    admin_group_name = make_virtual_lab_group_name(lab_id, UserRoleEnum.admin)
    member_group_name = make_virtual_lab_group_name(lab_id, UserRoleEnum.member)
    admin_group, member_group = await asyncio.gather(
        KeycloakRealm.a_create_group({"name": admin_group_name}),
        KeycloakRealm.a_create_group({"name": member_group_name}),
    )
    assert admin_group is not None
    assert member_group is not None
    return {
        "admin_group": {"id": admin_group, "name": admin_group_name},
        "member_group": {"id": member_group, "name": member_group_name},
    }


async def _provision_keycloak(
    ledger: Ledger,
    new_lab_id: UUID4,
    owner_id: UUID4,
    lab_name: str,
) -> GroupIds:
    async with provision(
        ledger,
        step_name="keycloak groups",
        on_failure=KeycloakGroupProvisioningError,
    ):
        try:
            groups = await _create_keycloak_groups(new_lab_id, lab_name)
        except IdentityError as err:
            raise UserNotAuthorizedToCreateVirtualLabError(
                owner_id=str(owner_id)
            ) from err
        ledger.push(await _make_kc_groups_compensation(groups))

    async with provision(
        ledger,
        step_name="keycloak group membership",
        on_failure=KeycloakGroupMembershipError,
    ):
        try:
            await KeycloakRealm.a_group_user_add(
                user_id=owner_id, group_id=groups["admin_group"]["id"]
            )
        except IdentityError as err:
            raise UserNotAuthorizedToCreateVirtualLabError(
                owner_id=str(owner_id)
            ) from err

    return groups


def _log_orphan_accounting_account(
    virtual_lab_id: UUID4,
) -> Callable[[], Awaitable[None]]:
    """Placeholder unwind for accounting account creation.

    The accounting service does not currently expose a delete-account
    endpoint.
    """

    async def _undo() -> None:
        logger.warning(
            f"Orphan accounting account left for vlab {virtual_lab_id}; "
            "no delete endpoint available — reconcile manually."
        )

    return _undo


async def _provision_accounting(
    ledger: Ledger,
    new_lab_id: UUID4,
    lab_name: str,
    welcome_bonus: Decimal,
) -> None:
    if settings.ACCOUNTING_BASE_URL is None:
        return
    async with provision(
        ledger,
        step_name="accounting account",
        on_failure=AccountingAccountProvisioningError,
    ):
        await accounting_cases.create_virtual_lab_account(
            virtual_lab_id=new_lab_id,
            name=lab_name,
            balance=welcome_bonus,
        )
        ledger.push(_log_orphan_accounting_account(new_lab_id))


async def _ensure_stripe_customer_id(*, user_id: UUID4, email: str, name: str) -> str:
    customer = await get_stripe_repository().create_customer(
        user_id=user_id, email=email, name=name
    )
    if customer is None:
        raise StripeCustomerCreationError(user_id)
    return customer.id


async def _provision_stripe_customer(
    ledger: Ledger,
    owner_id: UUID4,
    kc_user: dict[str, object],
    owner_email: str,
) -> str:
    async with provision(
        ledger,
        step_name="stripe customer",
        on_failure=StripeCustomerProvisioningError,
    ):
        return await _ensure_stripe_customer_id(
            user_id=owner_id,
            email=str(kc_user.get("email") or owner_email),
            name=f"{kc_user.get('firstName', '')} {kc_user.get('lastName', '')}",
        )


# persistence (single DB transaction)


async def _stage_stripe_user_if_missing(
    session: AsyncSession, *, user_id: UUID4, stripe_customer_id: str
) -> None:
    existing = await session.scalar(
        select(models.StripeUser).where(models.StripeUser.user_id == user_id)
    )
    if existing is None:
        session.add(
            models.StripeUser(user_id=user_id, stripe_customer_id=stripe_customer_id)
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


async def _insert_free_subscription(
    session: AsyncSession,
    *,
    user_id: UUID4,
    virtual_lab_id: UUID4,
    status: models.SubscriptionStatus,
) -> None:
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


# post-commit side effects
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

    await KeycloakRealm.a_update_user(user_id=user_id, payload=update_data)


async def _run_post_commit(
    owner_id: UUID4,
    virtual_lab_id: UUID4,
    owner_email: str | None,
) -> None:
    deferred = PostCommitActions()

    async def _update_kc_props() -> None:
        await _update_user_custom_properties(
            user_id=owner_id,
            properties=[
                ("plan", models.SubscriptionTierEnum.FREE.value, "multiple"),
                ("virtual_lab_id", str(virtual_lab_id), "multiple"),
            ],
        )

    deferred.add(_update_kc_props)

    if owner_email:

        async def _welcome() -> None:
            await send_welcome_email(owner_email)

        deferred.add(_welcome)

    await deferred.run()


@translate_domain_errors
async def create_virtual_lab(
    db: AsyncSession,
    virtual_lab_draft: domain.VirtualLabCreate,
    auth: tuple[AuthUserGrants, str],
    policy: VirtualLabCreationPolicy = REGULAR_LAB_POLICY,
) -> domain.VirtualLabDetails:
    owner_id = auth[0].id
    owner_email = auth[0].email
    virtual_lab_draft_id: UUID4 = uuid4()

    virtual_lab_draft = virtual_lab_draft.model_copy(
        update={"name": virtual_lab_draft.name.strip()}
    )
    kc_user = await _load_kc_user(owner_id)

    if policy.enforce_single_workspace:
        await _ensure_owner_has_no_virtual_lab(db, owner_id)
    await _ensure_name_available(db, virtual_lab_draft.name)
    await db.rollback()

    snapshot: domain.VirtualLabDetails
    stripe_customer_id: str | None = None
    async with ledger_container() as ledger:
        groups = await _provision_keycloak(
            ledger, virtual_lab_draft_id, owner_id, virtual_lab_draft.name
        )
        await _provision_accounting(
            ledger, virtual_lab_draft_id, virtual_lab_draft.name, policy.welcome_bonus
        )
        if policy.enable_billing:
            stripe_customer_id = await _provision_stripe_customer(
                ledger, owner_id, kc_user, owner_email
            )

        async with transactional_persistence(
            db,
            on_integrity_error=VirtualLabNameConflictError,
            on_db_error=VirtualLabPersistenceError,
        ):
            row = await _insert_virtual_lab(
                db,
                new_lab_id=virtual_lab_draft_id,
                owner_id=owner_id,
                owner_email=owner_email,
                admin_group_id=groups["admin_group"]["id"],
                member_group_id=groups["member_group"]["id"],
                payload=virtual_lab_draft,
            )
            snapshot = domain.VirtualLabDetails.model_validate(row)
            if policy.enable_billing:
                assert stripe_customer_id is not None
                await _stage_stripe_user_if_missing(
                    db, user_id=owner_id, stripe_customer_id=stripe_customer_id
                )
                await _insert_free_subscription(
                    db,
                    user_id=owner_id,
                    virtual_lab_id=virtual_lab_draft_id,
                    status=models.SubscriptionStatus.ACTIVE,
                )

    if policy.run_post_commit_actions:
        kc_email = kc_user.get("email")
        await _run_post_commit(
            owner_id,
            snapshot.id,
            str(kc_email) if kc_email else owner_email,
        )

    return snapshot
