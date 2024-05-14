from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from virtual_labs.infrastructure.db.models import (
    PaymentMethod as DbPaymentMethod,
)
from virtual_labs.infrastructure.db.models import (
    VirtualLab,
)
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.tests.utils import session_context_factory


@pytest.mark.asyncio
async def test_delete_payment_method_from_vl(
    async_test_client: AsyncClient,
    mock_create_payment_methods: tuple[
        dict[str, str], list[dict[str, str]], dict[str, str]
    ],
) -> None:
    client = async_test_client
    (virtual_lab, _, _) = mock_create_payment_methods

    async with session_context_factory() as session:
        payment_methods = list(
            (
                await session.execute(
                    statement=select(DbPaymentMethod).where(
                        DbPaymentMethod.virtual_lab_id == virtual_lab["id"]
                    )
                )
            ).scalars()
        )

    first_payment_method = payment_methods[0]
    response = await client.delete(
        "/virtual-labs/{}/billing/payment-methods/{}".format(
            virtual_lab["id"],
            str(first_payment_method.id),
        ),
    )

    assert response is not None
    assert response.status_code == 200
    assert response.json()["data"]["deleted"] is True

    async with session_context_factory() as session:
        db_virtual_lab = (
            await session.execute(
                statement=select(VirtualLab).filter(
                    VirtualLab.id == UUID(virtual_lab["id"])
                )
            )
        ).scalar_one()

        after_delete_payment_methods = list(
            (
                await session.execute(
                    statement=select(DbPaymentMethod).filter(
                        DbPaymentMethod.virtual_lab_id == UUID(virtual_lab["id"])
                    )
                )
            ).scalars()
        )

    assert len(after_delete_payment_methods) < len(payment_methods)

    stripe_customer_payment_methods = await stripe_client.payment_methods.list_async(
        params={
            "customer": str(db_virtual_lab.stripe_customer_id),
        }
    )

    assert len(stripe_customer_payment_methods.data) == len(
        after_delete_payment_methods
    )
