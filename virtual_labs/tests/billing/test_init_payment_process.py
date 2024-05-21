import pytest
from httpx import AsyncClient

new_credit = 5000  # in dollars


@pytest.mark.asyncio
async def test_init_payment_process(
    async_test_client: AsyncClient,
    mock_create_payment_method: tuple[dict[str, str], dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    virtual_lab, payment_method, headers = mock_create_payment_method
    virtual_lab_id = virtual_lab["id"]

    payment_method_id = payment_method["id"]
    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/billing/budget-topup",
        json={
            "payment_method_id": payment_method_id,
            "credit": new_credit,
        },
    )

    assert response is not None
    assert response.status_code == 200
