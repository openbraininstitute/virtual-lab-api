from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import (
    FreeSubscription,
    PaidSubscription,
    Subscription,
    SubscriptionStatus,
    SubscriptionType,
)


class SubscriptionRepository:
    """
    repository for subscription related database operations.
    """

    def __init__(self, db_session: AsyncSession) -> None:
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
    ) -> Optional[PaidSubscription]:
        """
        get a subscription by its Stripe subscription id.

        Args:
            stripe_subscription_id: Stripe subscription id

        Returns:
            The subscription if found, None otherwise
        """
        stmt = select(PaidSubscription).where(
            PaidSubscription.stripe_subscription_id == stripe_subscription_id
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
        self, user_id: UUID
    ) -> Optional[Subscription]:
        """get active subscription for a user."""
        stmt = select(Subscription).where(
            and_(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_free_subscription_by_user_id(
        self, user_id: UUID
    ) -> Optional[FreeSubscription]:
        """get free not active subscription for a user."""
        stmt = select(FreeSubscription).where(
            and_(
                Subscription.user_id == user_id,
                Subscription.status != SubscriptionStatus.ACTIVE,
            )
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def list_subscriptions(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[SubscriptionStatus] = None,
    ) -> list[Subscription]:
        """
        list subscriptions with optional filtering.

        Args:
            user_id: filter by user id
            status: Optional filter by subscription status

        Returns:
            List of subscriptions matching the filters
        """

        stmt = select(Subscription)

        filters = []
        if user_id:
            filters.append(Subscription.user_id == str(user_id))
        if status:
            filters.append(Subscription.status == status)

        if filters:
            stmt = stmt.where(*filters)

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

    async def create_free_subscription(
        self,
        user_id: UUID,
        virtual_lab_id: UUID,
    ) -> FreeSubscription:
        """Create a new free subscription."""
        subscription = FreeSubscription(
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            subscription_type=SubscriptionType.FREE,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime.now(),
            # Free subscriptions don't expire
            current_period_end=datetime.max,
        )
        self.db_session.add(subscription)
        await self.db_session.commit()
        await self.db_session.refresh(subscription)
        return subscription

    async def downgrade_to_free(
        self, paid_subscription: PaidSubscription
    ) -> FreeSubscription:
        """Downgrade a paid subscription to free."""
        free_subscription = await self.get_free_subscription_by_user_id(
            paid_subscription.user_id
        )
        if free_subscription:
            free_subscription.status = SubscriptionStatus.ACTIVE
            free_subscription.current_period_start = datetime.now()
            free_subscription.current_period_end = datetime.max
        else:
            free_subscription = FreeSubscription(
                user_id=paid_subscription.user_id,
                virtual_lab_id=paid_subscription.virtual_lab_id,
                subscription_type=SubscriptionType.FREE,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=datetime.now(),
                current_period_end=datetime.max,
            )
        self.db_session.add(free_subscription)
        await self.db_session.commit()
        await self.db_session.refresh(free_subscription)

        return free_subscription

    async def get_virtual_lab_subscription(
        self, virtual_lab_id: UUID
    ) -> Optional[Subscription]:
        """Get active subscription for a virtual lab."""
        stmt = select(Subscription).where(
            and_(
                Subscription.virtual_lab_id == virtual_lab_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_all_active_subscriptions(self) -> list[Subscription]:
        """Get all active subscriptions."""
        stmt = select(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE
        )
        result = await self.db_session.execute(stmt)
        return list(result.scalars().all())
