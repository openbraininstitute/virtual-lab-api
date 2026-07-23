from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, false, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from virtual_labs.domain.payment import PaymentFilter, PaymentType
from virtual_labs.infrastructure.db.models import SubscriptionPayment


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _apply_filters(
        self, query: Select[Tuple[SubscriptionPayment]], filters: PaymentFilter
    ) -> Select[Tuple[SubscriptionPayment]]:
        """apply filters to the query"""
        conditions = []

        if filters.start_date:
            conditions.append(SubscriptionPayment.payment_date >= filters.start_date)
        if filters.end_date:
            conditions.append(SubscriptionPayment.payment_date <= filters.end_date)
        if filters.card_last4:
            conditions.append(SubscriptionPayment.card_last4 == filters.card_last4)
        if filters.card_brand:
            conditions.append(SubscriptionPayment.card_brand == filters.card_brand)
        if filters.virtual_lab_id:
            conditions.append(
                SubscriptionPayment.virtual_lab_id == filters.virtual_lab_id
            )
        if filters.payment_type:
            if filters.payment_type == PaymentType.STANDALONE:
                conditions.append(SubscriptionPayment.standalone == true())
            elif filters.payment_type == PaymentType.SUBSCRIPTION:
                conditions.append(SubscriptionPayment.standalone == false())

        if conditions:
            query = query.where(and_(*conditions))

        return query

    async def admin_list_payments(
        self,
        filters: PaymentFilter,
        customer_id: Optional[str] = None,
    ) -> Tuple[List[SubscriptionPayment], int]:
        """`list_payments` without the mandatory customer scope, for
        the platform-admin namespace. Returns ``(payments, total)``.
        """
        query = select(SubscriptionPayment)
        if customer_id:
            query = query.where(SubscriptionPayment.customer_id == customer_id)
        query = self._apply_filters(query, filters)

        total = (
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
        ) or 0

        rows = (
            (
                await self.session.execute(
                    query.order_by(SubscriptionPayment.payment_date.desc())
                    .offset(filters.offset)
                    .limit(filters.page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def get_payment_by_id(
        self, payment_id: UUID
    ) -> Optional[SubscriptionPayment]:
        return await self.session.get(SubscriptionPayment, payment_id)

    async def list_payments(
        self,
        customer_id: str,
        filters: PaymentFilter,
    ) -> Tuple[List[SubscriptionPayment], int]:
        """
        list payments with filters
        returns a tuple of (payments, total_count)
        """
        subscription_query = select(SubscriptionPayment)
        subscription_query = subscription_query.where(
            SubscriptionPayment.customer_id == customer_id
        )

        subscription_query = self._apply_filters(subscription_query, filters)
        count_query = select(func.count()).select_from(subscription_query.subquery())
        total_count = await self.session.scalar(count_query) or 0

        subscription_query = (
            subscription_query.order_by(SubscriptionPayment.payment_date.desc())
            .offset(filters.offset)
            .limit(filters.page_size)
        )

        subscription_result = await self.session.execute(subscription_query)
        subscription_payments = list(subscription_result.scalars().all())
        return subscription_payments, total_count
