from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, HTTPStatusError, Response

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.interfaces.discount_interface import (
    DiscountInterface,
)
from virtual_labs.external.accounting.models import (
    CreateDiscountResponse,
)
from virtual_labs.infrastructure.settings import settings


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def discount_interface(mock_client: AsyncMock) -> DiscountInterface:
    return DiscountInterface(client=mock_client, client_token="test-token")


@pytest.mark.asyncio
async def test_api_url(discount_interface: DiscountInterface) -> None:
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/discount"
    assert discount_interface._api_url == expected_url


@pytest.mark.asyncio
async def test_create_virtual_lab_discount_success(
    discount_interface: DiscountInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    valid_from = datetime.now(UTC)
    valid_to = valid_from + timedelta(hours=1)

    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Discount created",
        "data": {
            "id": 1,
            "vlab_id": vlab_id,
            "discount": "0.2",
            "valid_from": str(valid_from),
            "valid_to": str(valid_to),
        },
    }
    mock_client.post.return_value = mock_response

    result = await discount_interface.create_discount(
        vlab_id, Decimal("0.2"), valid_from, valid_to
    )

    assert isinstance(result, CreateDiscountResponse)
    assert result.data.vlab_id == vlab_id
    assert result.data.discount == Decimal("0.2")

    mock_client.post.assert_called_once()

    expected_url = f"{settings.ACCOUNTING_BASE_URL}/discount"
    assert mock_client.post.call_args[0][0] == expected_url


@pytest.mark.asyncio
async def test_create_virtual_lab_discount_http_error(
    discount_interface: DiscountInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    valid_from = datetime.now(UTC)
    valid_to = valid_from + timedelta(hours=1)

    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await discount_interface.create_discount(
            vlab_id, Decimal("0.2"), valid_from, valid_to
        )

    assert exc_info.value.type == AccountingErrorValue.CREATE_VIRTUAL_LAB_DISCOUNT_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_create_virtual_lab_discount_general_error(
    discount_interface: DiscountInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    valid_from = datetime.now(UTC)
    valid_to = valid_from + timedelta(hours=1)

    mock_client.post.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await discount_interface.create_discount(
            vlab_id, Decimal("0.2"), valid_from, valid_to
        )

    assert exc_info.value.type == AccountingErrorValue.CREATE_VIRTUAL_LAB_DISCOUNT_ERROR
    assert exc_info.value.http_status_code is None
