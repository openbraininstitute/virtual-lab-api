from uuid import UUID

from loguru import logger

from virtual_labs.core.exceptions.generic_exceptions import EntityNotCreated
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)


async def ensure_stripe_customer(
    user_id: UUID,
    email: str,
    name: str,
    stripe_service: StripeRepository,
    stripe_user_query_repo: StripeUserQueryRepository,
    stripe_user_mutation_repo: StripeUserMutationRepository,
) -> str:
    """Ensure a Stripe customer exists for the given user. Creates one if needed,
    updates the existing one otherwise.

    Returns:
        The Stripe customer ID.

    Raises:
        EntityNotCreated: If customer creation fails.
    """
    customer = await stripe_user_query_repo.get_by_user_id(user_id=user_id)

    if customer is None:
        stripe_customer = await stripe_service.create_customer(
            user_id=user_id,
            email=email,
            name=name,
        )
        if stripe_customer is None:
            raise EntityNotCreated("Stripe customer creation failed")

        await stripe_user_mutation_repo.create(
            user_id=user_id,
            stripe_customer_id=stripe_customer.id,
        )
        logger.info(f"Created Stripe customer {stripe_customer.id} for user {user_id}")
        return stripe_customer.id

    assert customer.stripe_customer_id, (
        "Customer record exists but has no stripe_customer_id"
    )
    await stripe_service.update_customer(
        customer_id=customer.stripe_customer_id,
        name=name,
        email=email,
    )
    return customer.stripe_customer_id
