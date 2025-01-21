from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, HTTPStatusError, Response

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.balance_interface import BalanceInterface
from virtual_labs.external.accounting.models import (
    ProjBalanceResponse,
    VlabBalanceResponse,
)
from virtual_labs.infrastructure.settings import settings


@pytest.fixture
def mock_client():
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def balance_interface(mock_client):
    return BalanceInterface(client=mock_client, client_token="test-token")


@pytest.mark.asyncio
async def test_api_url(balance_interface):
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/balance"
    assert balance_interface._api_url == expected_url


@pytest.mark.asyncio
async def test_get_virtual_lab_balance_success(balance_interface, mock_client):
    vlab_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Balance for virtual-lab including projects",
        "data": {
            "vlab_id": str(vlab_id),
            "balance": "1000",
            "projects": [
                {
                    "proj_id": "8eb248a8-672c-4158-9365-b95286cba796",
                    "balance": "9763.40",
                    "reservation": "0.00",
                }
            ],
        },
    }
    mock_client.get.return_value = mock_response

    result = await balance_interface.get_virtual_lab_balance(vlab_id)

    assert isinstance(result, VlabBalanceResponse)
    assert result.data.vlab_id == vlab_id

    mock_client.get.assert_called_once()

    call_args = mock_client.get.call_args[0]
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/balance/virtual-lab/{vlab_id}"
    assert call_args[0] == expected_url


@pytest.mark.asyncio
async def test_get_virtual_lab_balance_http_error(balance_interface, mock_client):
    vlab_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.get.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await balance_interface.get_virtual_lab_balance(vlab_id)

    assert exc_info.value.type == AccountingErrorValue.FETCH_VIRTUAL_LAB_BALANCE_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_get_virtual_lab_balance_general_error(balance_interface, mock_client):
    vlab_id = uuid4()
    mock_client.get.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await balance_interface.get_virtual_lab_balance(vlab_id)

    assert exc_info.value.type == AccountingErrorValue.FETCH_VIRTUAL_LAB_BALANCE_ERROR


@pytest.mark.asyncio
async def test_get_project_balance_success(balance_interface, mock_client):
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Balance for project",
        "data": {"proj_id": str(project_id), "balance": "100", "reservation": "15.20"},
    }
    mock_client.get.return_value = mock_response

    result = await balance_interface.get_project_balance(project_id)

    assert isinstance(result, ProjBalanceResponse)
    assert result.data.proj_id == project_id

    mock_client.get.assert_called_once()

    call_args = mock_client.get.call_args[0]
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/balance/project/{project_id}"
    assert call_args[0] == expected_url


@pytest.mark.asyncio
async def test_get_project_balance_http_error(balance_interface, mock_client):
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.get.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await balance_interface.get_project_balance(project_id)

    assert exc_info.value.type == AccountingErrorValue.FETCH_PROJECT_BALANCE_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_get_project_balance_general_error(balance_interface, mock_client):
    project_id = uuid4()
    mock_client.get.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await balance_interface.get_project_balance(project_id)

    assert exc_info.value.type == AccountingErrorValue.FETCH_PROJECT_BALANCE_ERROR
