from datetime import datetime
from typing import Literal, Optional, Union, overload
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import with_polymorphic

from virtual_labs.infrastructure.db.models import (
    FreeSubscription,
    PaidSubscription,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    SubscriptionTierEnum,
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

    async def get_active_subscription_by_user_id(
        self, user_id: UUID, subscription_type: Optional[Literal["free", "paid"]] = None
    ) -> Optional[Subscription]:
        """
        get active subscription for a user (type free or paid)

        Args:
            user_id: The ID of the user
            subscription_type: Optional filter by subscription type ("free" or "paid")

        Returns:
            The active subscription if found, None otherwise
        """
        filters = [
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        ]

        if subscription_type:
            if subscription_type.lower() == "free":
                free_stmt = (
                    select(FreeSubscription)
                    .where(and_(*filters))
                    .order_by(FreeSubscription.created_at.desc())
                )
                result = await self.db_session.execute(free_stmt)
                return result.scalars().first()
            elif subscription_type.lower() == "paid":
                paid_stmt = (
                    select(PaidSubscription)
                    .where(and_(*filters))
                    .order_by(PaidSubscription.created_at.desc())
                )
                result = await self.db_session.execute(paid_stmt)
                return result.scalars().first()

        stmt = (
            select(Subscription)
            .where(and_(*filters))
            .order_by(Subscription.created_at.desc())
        )
        result = await self.db_session.execute(stmt)

        return result.scalars().first()

    async def get_free_subscription_by_user_id(
        self, user_id: UUID, status: Optional[SubscriptionStatus] = None
    ) -> Optional[FreeSubscription]:
        """
        get free subscription for a user with optional status filtering.

        Args:
            user_id: The ID of the user
            status: Optional filter by subscription status. If None, returns non-active subscriptions.

        Returns:
            The free subscription if found, None otherwise
        """
        filters = [FreeSubscription.user_id == user_id]

        if status:
            # Filter by the specific status provided
            filters.append(FreeSubscription.status == status)

        stmt = select(FreeSubscription).where(and_(*filters))
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    @overload
    async def list_subscriptions(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[SubscriptionStatus] = None,
        subscription_type: Literal["free"] = "free",
    ) -> list[FreeSubscription]:
        ...

    @overload
    async def list_subscriptions(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[SubscriptionStatus] = None,
        subscription_type: Literal["paid"] = "paid",
    ) -> list[PaidSubscription]:
        ...

    async def list_subscriptions(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[SubscriptionStatus] = None,
        subscription_type: Optional[str] = None,
    ) -> Union[list[Subscription], list[FreeSubscription], list[PaidSubscription]]:
        """
        list subscriptions with optional filtering.

        Args:
            user_id: filter by user id
            status: Optional filter by subscription status
            subscription_type: Optional filter by subscription type ("free" or "paid")

        Returns:
            list of subscriptions matching the filters. Returns specific subscription types
            (FreeSubscription or PaidSubscription) when subscription_type is specified.
        """
        if subscription_type:
            if subscription_type.lower() == "free":
                # Query specifically for FreeSubscription
                stmt = select(FreeSubscription)
                filters = []
                if user_id:
                    filters.append(FreeSubscription.user_id == user_id)
                if status:
                    filters.append(FreeSubscription.status == status)
                if filters:
                    stmt = stmt.where(*filters)
                stmt = stmt.order_by(FreeSubscription.created_at.desc())
                result = await self.db_session.execute(stmt)
                return list(result.scalars().all())
            elif subscription_type.lower() == "paid":
                stmt = select(PaidSubscription)
                filters = []
                if user_id:
                    filters.append(PaidSubscription.user_id == user_id)
                if status:
                    filters.append(PaidSubscription.status == status)
                if filters:
                    stmt = stmt.where(*filters)
                stmt = stmt.order_by(PaidSubscription.created_at.desc())
                result = await self.db_session.execute(stmt)
                return list(result.scalars().all())

        poly_subscription = with_polymorphic(
            Subscription, [FreeSubscription, PaidSubscription]
        )
        stmt = select(poly_subscription)

        filters = []
        if user_id:
            filters.append(poly_subscription.user_id == user_id)
        if status:
            filters.append(poly_subscription.status == status)

        if filters:
            stmt = stmt.where(*filters)

        stmt = stmt.order_by(poly_subscription.created_at.desc())

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
        tier = await self.get_subscription_tier_by_tier(tier=SubscriptionTierEnum.FREE)
        if tier is None:
            raise ValueError("Free subscription tier not found")
        subscription = FreeSubscription(
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            tier_id=tier.id,
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
        self,
        user_id: UUID,
    ) -> FreeSubscription:
        """Downgrade a paid subscription to free."""
        free_subscription = await self.get_free_subscription_by_user_id(user_id)
        if free_subscription:
            free_subscription.status = SubscriptionStatus.ACTIVE
            free_subscription.current_period_start = datetime.now()
            free_subscription.current_period_end = datetime.max
            free_subscription.usage_count += 1
        else:
            free_subscription = FreeSubscription(
                user_id=user_id,
                subscription_type=SubscriptionType.FREE,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=datetime.now(),
                current_period_end=datetime.max,
            )

        self.db_session.add(free_subscription)
        await self.db_session.commit()
        await self.db_session.refresh(free_subscription)

        return free_subscription

    async def deactivate_free_subscription(
        self,
        user_id: UUID,
    ) -> Optional[FreeSubscription]:
        """
        deactivate a user's free subscription.
        called when upgrading a user to a paid plan.

        Args:
            user_id: the user id

        Returns:
            the deactivated free subscription if found, none otherwise
        """

        free_subscription = await self.get_free_subscription_by_user_id(
            user_id, status=SubscriptionStatus.ACTIVE
        )

        if free_subscription:
            free_subscription.status = SubscriptionStatus.PAUSED
            self.db_session.add(free_subscription)
            await self.db_session.commit()
            await self.db_session.refresh(free_subscription)
            return free_subscription

        return None

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

    # get subscription plan by id
    async def get_subscription_tier_by_id(
        self, subscription_tier_id: UUID
    ) -> Optional[SubscriptionTier]:
        """get subscription tier by id."""

        stmt = select(SubscriptionTier).where(
            SubscriptionTier.id == subscription_tier_id
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_subscription_tier_by_product_id(
        self, product_id: str
    ) -> Optional[SubscriptionTier]:
        """get subscription tier by product id."""
        stmt = select(SubscriptionTier).where(
            SubscriptionTier.stripe_product_id == product_id
        )
        result = await self.db_session.execute(stmt)
        return result.scalars().first()

    async def get_subscription_tier_by_tier(
        self, tier: SubscriptionTierEnum
    ) -> Optional[SubscriptionTier]:
        """get subscription tier by tier."""
        stmt = select(SubscriptionTier).where(SubscriptionTier.tier == tier)
        result = await self.db_session.execute(stmt)
        return result.scalars().first()
