from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.stripe.webhook import StripeWebhook
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository


def get_stripe_repository() -> StripeRepository:
    """
    dependency for getting the Stripe repository.
    """

    return StripeRepository()


def get_subscription_repository(
    session: AsyncSession = Depends(default_session_factory),
) -> SubscriptionRepository:
    """
    dependency for getting the db subscription repository.
    """

    return SubscriptionRepository(
        db_session=session,
    )


def get_stripe_webhook_service(
    stripe_repository: StripeRepository = Depends(get_stripe_repository),
    subscription_repository: SubscriptionRepository = Depends(
        get_subscription_repository
    ),
) -> StripeWebhook:
    """
    dependency for getting the Stripe webhook service.
    """

    return StripeWebhook(
        stripe_repository=stripe_repository,
        subscription_repository=subscription_repository,
    )
