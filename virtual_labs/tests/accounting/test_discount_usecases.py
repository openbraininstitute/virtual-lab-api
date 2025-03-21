from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from virtual_labs.external.accounting.models import CreateDiscountResponse
from virtual_labs.usecases.accounting import create_virtual_lab_discount


@pytest.mark.asyncio
async def test_create_virtual_lab_discount() -> None:
    vlab_id = uuid4()
    valid_from = datetime.now(UTC)
    valid_to = valid_from + timedelta(hours=1)

    mock_response_data = {
        "message": "Discount created",
        "data": {
            "id": 1,
            "vlab_id": vlab_id,
            "discount": "0.2",
            "valid_from": str(valid_from),
            "valid_to": str(valid_to),
        },
    }

    with patch("httpx.AsyncClient") as mock_client, patch(
        "virtual_labs.infrastructure.kc.auth.get_client_token"
    ) as mock_token:
        mock_token.return_value = "test-token"

        mock_response = AsyncMock()
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None

        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await create_virtual_lab_discount(
            vlab_id, Decimal("0.2"), valid_from, valid_to
        )

        assert isinstance(result, CreateDiscountResponse)
        assert result.data.vlab_id == vlab_id
        assert result.data.discount == Decimal("0.2")
        assert result.data.valid_from == valid_from
        assert result.data.valid_to == valid_to
