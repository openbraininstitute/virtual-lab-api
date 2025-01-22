from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from virtual_labs.external.accounting.models import (
    ProjBalanceResponse,
    VlabBalanceResponse,
)
from virtual_labs.usecases.accounting import (
    get_project_balance,
    get_virtual_lab_balance,
)


@pytest.mark.asyncio
async def test_get_virtual_lab_balance() -> None:
    virtual_lab_id = uuid4()
    mock_response_data = {
        "message": "Virtual lab balance retrieved",
        "data": {"vlab_id": str(virtual_lab_id), "balance": "1000.0"},
    }

    with patch("httpx.AsyncClient") as mock_client, patch(
        "virtual_labs.infrastructure.kc.auth.get_client_token"
    ) as mock_token:
        mock_token.return_value = "test-token"

        mock_response = AsyncMock()
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None

        client_instance = AsyncMock()
        client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await get_virtual_lab_balance(virtual_lab_id)

        assert isinstance(result, VlabBalanceResponse)
        assert result.data.vlab_id == virtual_lab_id
        assert result.data.balance == "1000.0"


@pytest.mark.asyncio
async def test_get_project_balance() -> None:
    project_id = uuid4()
    mock_response_data = {
        "message": "Project balance retrieved",
        "data": {"balance": "500.0", "reservation": "0", "proj_id": str(project_id)},
    }

    with patch("httpx.AsyncClient") as mock_client, patch(
        "virtual_labs.infrastructure.kc.auth.get_client_token"
    ) as mock_token:
        mock_token.return_value = "test-token"

        mock_response = AsyncMock()
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None

        client_instance = AsyncMock()
        client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await get_project_balance(project_id)

        assert isinstance(result, ProjBalanceResponse)
        assert result.data.proj_id == project_id
        assert result.data.balance == "500.0"
        assert result.data.reservation == "0"
