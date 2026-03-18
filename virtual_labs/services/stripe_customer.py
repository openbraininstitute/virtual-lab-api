from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.generic_exceptions import EntityNotCreated
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)


async def ensure_stripe_customer(
    session: AsyncSession,
    user_id: UUID,
    email: str,
    name: str,
) -> str:
    """Ensure a Stripe customer exists for the given user. Creates one if needed,
    updates the existing one otherwise.

    Returns:
        The Stripe customer ID.

    Raises:
        EntityNotCreated: If customer creation fails.
    """
    ss: StripeRepository = StripeRepository()
    suqr: StripeUserQueryRepository = StripeUserQueryRepository(db_session=session)
    sumr: StripeUserMutationRepository = StripeUserMutationRepository(
        db_session=session
    )

    customer = await suqr.get_by_user_id(
        user_id=user_id,
    )

    if customer is None:
        stripe_customer = await ss.create_customer(
            user_id=user_id,
            email=email,
            name=name,
        )
        if stripe_customer is None:
            raise EntityNotCreated("Stripe customer creation failed")

        await sumr.create(
            user_id=user_id,
            stripe_customer_id=stripe_customer.id,
        )
        logger.info(f"Created Stripe customer {stripe_customer.id} for user {user_id}")
        return stripe_customer.id

    assert customer.stripe_customer_id, (
        "Customer record exists but has no stripe_customer_id"
    )
    await ss.update_customer(
        customer_id=customer.stripe_customer_id,
        name=name,
        email=email,
    )

    return customer.stripe_customer_id
