from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.shared.utils.billing import amount_to_cent
from virtual_labs.tests.utils import session_context_factory


@pytest.mark.asyncio
async def test_retrieve_vl_init_balance(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    response, headers = mock_lab_create
    virtual_lab_id = response.json()["data"]["virtual_lab"]["id"]

    response = await client.get(
        f"/virtual-labs/{virtual_lab_id}/billing/balance",
    )

    assert response is not None
    assert response.status_code == 200
    assert response.json()["data"]["budget"] == 0
    assert response.json()["data"]["total_spent"] == 0


@pytest.mark.asyncio
async def test_retrieve_vl_balance_after_topup(
    async_test_client: AsyncClient,
    mock_create_payment_method: tuple[dict[str, str], dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    virtual_lab, payment_method, headers = mock_create_payment_method
    virtual_lab_id = virtual_lab["id"]

    payment_method_id = payment_method["id"]
    new_budget = 5000

    await client.post(
        f"/virtual-labs/{virtual_lab_id}/billing/budget-topup",
        json={
            "payment_method_id": payment_method_id,
            "credit": new_budget,
        },
    )

    async with session_context_factory() as session:
        await session.execute(
            statement=update(VirtualLab)
            .filter(VirtualLab.id == UUID(virtual_lab_id))
            .values(budget_amount=amount_to_cent(new_budget))
        )
        await session.commit()

    response = await client.get(
        f"/virtual-labs/{virtual_lab_id}/billing/balance",
    )

    data = response.json()["data"]

    assert response is not None
    assert response.status_code == 200
    assert data["budget"] == new_budget
    assert data["total_spent"] < new_budget
