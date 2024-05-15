from typing import cast
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from virtual_labs.domain.payment_method import PaymentMethod
from virtual_labs.infrastructure.db.models import (
    PaymentMethod as DbPaymentMethod,
)
from virtual_labs.infrastructure.db.models import (
    VirtualLab,
)
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.tests.utils import session_context_factory


async def get_lab_and_payment_methods_details(
    lab_id: str, updated_pm: UUID, other_pm_ids: list[str]
) -> tuple[VirtualLab, DbPaymentMethod, list[DbPaymentMethod]]:
    async with session_context_factory() as session:
        db_virtual_lab = (
            await session.execute(
                statement=select(VirtualLab).filter(VirtualLab.id == UUID(lab_id))
            )
        ).scalar_one()

        payment_method = (
            await session.execute(
                statement=select(DbPaymentMethod).filter(
                    DbPaymentMethod.id == str(updated_pm)
                )
            )
        ).scalar_one()

        other_payment_methods = list(
            (
                await session.execute(
                    statement=select(DbPaymentMethod).filter(
                        DbPaymentMethod.id.in_(other_pm_ids)
                    )
                )
            ).scalars()
        )

    return (db_virtual_lab, payment_method, other_payment_methods)


@pytest.mark.asyncio
async def test_update_payment_method_default_status(
    async_test_client: AsyncClient,
    mock_create_payment_methods: tuple[
        dict[str, str], list[dict[str, str]], dict[str, str]
    ],
) -> None:
    client = async_test_client
    (virtual_lab, _, _) = mock_create_payment_methods

    response = await client.get(
        f"/virtual-labs/{virtual_lab["id"]}/billing/payment-methods"
    )
    payment_methods = cast(
        list[PaymentMethod], response.json()["data"]["payment_methods"]
    )

    first_payment_method_id = PaymentMethod.model_validate(payment_methods[0]).id
    second_payment_method_id = PaymentMethod.model_validate(payment_methods[1]).id
    other_payment_methods_ids = [
        str(PaymentMethod.model_validate(pm).id) for pm in payment_methods[1:]
    ]

    response = await client.patch(
        f"/virtual-labs/{virtual_lab["id"]}/billing/payment-methods/default",
        json={
            "payment_method_id": str(first_payment_method_id),
        },
    )
    assert response is not None
    assert response.status_code == 200

    (
        db_virtual_lab,
        payment_method,
        other_payment_methods,
    ) = await get_lab_and_payment_methods_details(
        virtual_lab["id"], first_payment_method_id, other_payment_methods_ids
    )

    stripe_customer = await stripe_client.customers.retrieve_async(
        str(db_virtual_lab.stripe_customer_id)
    )
    assert stripe_customer.invoice_settings is not None
    assert stripe_customer.invoice_settings.default_payment_method == str(
        payment_method.stripe_payment_method_id
    )
    assert payment_method.default is True

    for i in other_payment_methods:
        assert i.default is False

    # make the second one as default will update
    response = await client.patch(
        f"/virtual-labs/{virtual_lab["id"]}/billing/payment-methods/default",
        json={
            "payment_method_id": str(second_payment_method_id),
        },
    )

    assert response is not None
    assert response.status_code == 200
    other_payment_methods_ids = [
        str(PaymentMethod.model_validate(pm).id)
        for pm in list(
            filter(
                lambda x: str(x["id"]) != str(second_payment_method_id), payment_methods
            )
        )
    ]

    (
        db_virtual_lab,
        payment_method,
        other_payment_methods,
    ) = await get_lab_and_payment_methods_details(
        virtual_lab["id"], second_payment_method_id, other_payment_methods_ids
    )

    stripe_customer = await stripe_client.customers.retrieve_async(
        str(db_virtual_lab.stripe_customer_id)
    )
    assert stripe_customer.invoice_settings is not None
    assert stripe_customer.invoice_settings.default_payment_method == str(
        payment_method.stripe_payment_method_id
    )
    assert payment_method.default is True

    for i in other_payment_methods:
        assert i.default is False
