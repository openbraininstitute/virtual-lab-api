import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_retrieve_vl_payment_methods(
    async_test_client: AsyncClient,
    mock_create_payment_methods: tuple[
        dict[str, str], list[dict[str, str]], dict[str, str]
    ],
) -> None:
    client = async_test_client
    (virtual_lab, payment_methods, _) = mock_create_payment_methods

    response = await client.get(
        f"/virtual-labs/{virtual_lab["id"]}/billing/payment-methods",
    )

    assert response is not None
    assert response.status_code == 200
    assert response.json()["data"]["virtual_lab_id"] == virtual_lab["id"]
    assert len(response.json()["data"]["payment_methods"]) == len(payment_methods)
