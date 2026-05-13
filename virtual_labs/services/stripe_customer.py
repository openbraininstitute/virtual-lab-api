from __future__ import annotations

from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.billing import BillingAddress
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)


class StripeCustomerCreationError(RuntimeError):
    """Stripe rejected (or failed) the customer create call."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"Could not create Stripe customer for user {user_id}")
        self.user_id = user_id


class StripeCustomerService:
    """Find-or-create the Stripe customer for a user, transaction-friendly.

    The same `(check StripeUser → create Stripe customer → insert
    local row)` dance was duplicated in three usecases, each with
    its own subtle differences and orphan risk: if the local DB
    insert failed after the Stripe call succeeded, the customer
    existed in Stripe with no local link.

    This service is the canonical implementation. Callers wrap the
    `ensure_customer_for_user` call in their own
    `async with session.begin():` so the local row participates in
    the surrounding transaction; if their later work fails the row
    rolls back together with everything else. The Stripe customer
    itself stays — harmless on its own — and the next attempt finds
    it via the deterministic Stripe idempotency key on create rather
    than minting a duplicate.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        stripe_repository: StripeRepository | None = None,
    ) -> None:
        self.session = session
        self.query_repo = StripeUserQueryRepository(db_session=session)
        self.mutation_repo = StripeUserMutationRepository(db_session=session)
        self.stripe = stripe_repository or get_stripe_repository()

    async def ensure_customer_for_user(
        self,
        user_id: UUID,
        *,
        email: str,
        name: str,
        address: BillingAddress | None = None,
        validate_tax_location: bool = False,
        update_existing: bool = False,
    ) -> tuple[str, bool]:
        """Return `(stripe_customer_id, was_created)`.

        - Existing `StripeUser` → returns its customer id and
          `False`. If `update_existing=True` we also push the
          provided `email`/`name` (and `address` if any) to the
          Stripe customer, keeping it in sync with our user record.
        - Otherwise creates a Stripe customer with a deterministic
          idempotency key derived from `user_id`, stages the
          `StripeUser` row in the current transaction, and returns
          the new id and `True`.

        The local row is **flushed but not committed** — the
        caller's outer transaction (explicit `session.begin()` or
        autobegin closed by a later `await session.commit()`)
        controls the boundary. If the caller's later work raises
        before commit, the staged row rolls back with it.

        We deliberately do not return the ORM `StripeUser` itself —
        only the customer-id string and a `was_created` flag, both
        primitives, so callers can read them safely after the
        surrounding transaction commits without tripping over
        SQLAlchemy's `expire_on_commit` lazy-load.
        """
        existing = await self.query_repo.get_by_user_id(user_id)
        if existing is not None and existing.stripe_customer_id:
            existing_customer_id: str = existing.stripe_customer_id
            if update_existing:
                # Best-effort sync of email/name with the current
                # user record. Done outside any explicit DB txn —
                # purely a Stripe API call, no local writes.
                await self.stripe.update_customer(
                    customer_id=existing_customer_id,
                    email=email,
                    name=name,
                    address=address,
                    validate_tax_location=validate_tax_location,
                )
            return existing_customer_id, False

        customer = await self.stripe.create_customer(
            user_id=user_id,
            email=email,
            name=name,
            address=address,
            validate_tax_location=validate_tax_location,
        )
        if customer is None:
            # `create_customer` swallows non-tax errors and returns
            # None — surface the failure so the orchestrator's
            # transaction rolls back cleanly.
            raise StripeCustomerCreationError(user_id)

        await self.mutation_repo.stage(
            user_id=user_id,
            stripe_customer_id=customer.id,
        )
        logger.info(f"Created Stripe customer {customer.id} for user {user_id}")
        return customer.id, True
