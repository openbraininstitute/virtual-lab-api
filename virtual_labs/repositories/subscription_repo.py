from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Subscription, SubscriptionStatus


class SubscriptionRepository:
    """
    repository for subscription related database operations.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def get_subscription_by_id(
        self, subscription_id: UUID
    ) -> Optional[Subscription]:
        """
        get a subscription by its id.

        Args:
            subscription_id: the id of the subscription

        Returns:
            the subscription if found, None otherwise
        """
        stmt = select(Subscription).where(Subscription.id == subscription_id)
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_subscription_by_stripe_id(
        self, stripe_subscription_id: str
    ) -> Optional[Subscription]:
        """
        get a subscription by its Stripe subscription id.

        Args:
            stripe_subscription_id: Stripe subscription id

        Returns:
            The subscription if found, None otherwise
        """
        stmt = select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_active_subscription_by_lab_id(
        self, virtual_lab_id: UUID
    ) -> Optional[Subscription]:
        """
        get the active subscription for a virtual lab.

        Args:
            virtual_lab_id: The id of the virtual lab

        Returns:
            the active subscription if found, None otherwise
        """
        stmt = select(Subscription).where(
            Subscription.virtual_lab_id == virtual_lab_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_active_subscription_by_user_id(
        self, user_id: str
    ) -> Optional[Subscription]:
        """Get the active subscription for a user"""
        query = (
            select(Subscription)
            .where(
                and_(
                    Subscription.user_id == user_id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    Subscription.cancel_at_period_end == false(),
                )
            )
            .order_by(Subscription.created_at.desc())
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def list_subscriptions(
        self,
        status: Optional[SubscriptionStatus] = None,
    ) -> List[Subscription]:
        """
        list subscriptions with optional filtering.

        Args:
            virtual_lab_id: Optional filter by virtual lab ID
            user_id: Optional filter by user ID
            status: Optional filter by subscription status

        Returns:
            List of subscriptions matching the filters
        """
        stmt = select(Subscription)

        if status:
            stmt = stmt.where(Subscription.status == status)

        stmt = stmt.order_by(Subscription.created_at.desc())

        result = await self.db_session.execute(stmt)
        return list(result.scalars().all())

    async def create_subscription(self, subscription: Subscription) -> Subscription:
        """
        create a new subscription.

        Args:
            subscription: subscription to create

        Returns:
            the created subscription with its id
        """
        self.db_session.add(subscription)
        await self.db_session.commit()
        await self.db_session.refresh(subscription)
        return subscription

    async def update_subscription(self, subscription: Subscription) -> Subscription:
        """
        update an existing subscription.

        Args:
            subscription: subscription to update

        Returns:
            the updated subscription
        """
        self.db_session.add(subscription)
        await self.db_session.commit()
        await self.db_session.refresh(subscription)
        return subscription
