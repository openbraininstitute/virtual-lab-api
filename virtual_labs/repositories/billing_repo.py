from typing import List

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import PaymentMethod


class BillingQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def retrieve_vl_payment_methods(
        self,
        virtual_lab_id: UUID4,
    ) -> List[PaymentMethod]:
        query = select(PaymentMethod).where(
            PaymentMethod.virtual_lab_id == virtual_lab_id,
        )
        result = (
            (
                await self.session.execute(
                    statement=query.order_by(PaymentMethod.updated_at)
                )
            )
            .scalars()
            .all()
        )

        payment_cards = [row for row in result]
        return payment_cards


class BillingMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_new_payment_method(
        self,
        *,
        virtual_lab_id: UUID4,
        user_id: UUID4,
        payment_method_id: str,
        customer_id: str,
        card_number: str,
        expire_at: str,
        brand: str,
        cardholder_name: str,
        cardholder_email: str,
    ) -> PaymentMethod:
        payment_method = PaymentMethod(
            stripe_payment_method_id=payment_method_id,
            user_id=user_id,
            customerId=customer_id,
            card_number=card_number,
            brand=brand,
            cardholder_name=cardholder_name,
            cardholder_email=cardholder_email,
            expire_at=expire_at,
            virtual_lab_id=virtual_lab_id,
        )

        self.session.add(payment_method)
        await self.session.commit()
        await self.session.refresh(payment_method)
        return payment_method
