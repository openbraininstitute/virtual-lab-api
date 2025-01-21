from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, HTTPStatusError, Response

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.budget_interface import BudgetInterface
from virtual_labs.external.accounting.models import (
    BudgetAssignResponse,
    BudgetMoveResponse,
    BudgetReverseResponse,
    BudgetTopUpResponse,
)
from virtual_labs.infrastructure.settings import settings


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def budget_interface(mock_client: AsyncMock) -> BudgetInterface:
    return BudgetInterface(client=mock_client, client_token="test-token")


@pytest.mark.asyncio
async def test_api_url(budget_interface: BudgetInterface) -> None:
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/budget"
    assert budget_interface._api_url == expected_url


@pytest.mark.asyncio
async def test_top_up_success(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    amount = 1000.0
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Top-up operation executed",
        "data": None,
    }
    mock_client.post.return_value = mock_response

    result = await budget_interface.top_up(vlab_id, amount)

    assert isinstance(result, BudgetTopUpResponse)

    mock_client.post.assert_called_once()

    call_args = mock_client.post.call_args[0]
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/budget/top-up"
    assert call_args[0] == expected_url


@pytest.mark.asyncio
async def test_assign_success(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    amount = 500.0
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Assign budget operation executed",
        "data": None,
    }
    mock_client.post.return_value = mock_response

    result = await budget_interface.assign(vlab_id, project_id, amount)

    assert isinstance(result, BudgetAssignResponse)

    mock_client.post.assert_called_once()

    call_args = mock_client.post.call_args[0]
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/budget/assign"
    assert call_args[0] == expected_url


@pytest.mark.asyncio
async def test_reverse_success(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    amount = 300.0
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Reverse budget operation executed",
        "data": None,
    }
    mock_client.post.return_value = mock_response

    result = await budget_interface.reverse(vlab_id, project_id, amount)

    assert isinstance(result, BudgetReverseResponse)

    mock_client.post.assert_called_once()

    call_args = mock_client.post.call_args[0]
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/budget/reverse"
    assert call_args[0] == expected_url


@pytest.mark.asyncio
async def test_move_success(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    from_project = uuid4()
    to_project = uuid4()
    amount = 200.0
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Move budget operation executed",
        "data": None,
    }
    mock_client.post.return_value = mock_response

    result = await budget_interface.move(vlab_id, from_project, to_project, amount)

    assert isinstance(result, BudgetMoveResponse)

    mock_client.post.assert_called_once()

    call_args = mock_client.post.call_args[0]
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/budget/move"
    assert call_args[0] == expected_url


@pytest.mark.asyncio
async def test_top_up_http_error(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await budget_interface.top_up(vlab_id, 100.0)

    assert exc_info.value.type == AccountingErrorValue.TOP_UP_VIRTUAL_LAB_ACCOUNT_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_assign_http_error(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await budget_interface.assign(vlab_id, project_id, 100.0)

    assert exc_info.value.type == AccountingErrorValue.ASSIGN_PROJECT_BUDGET_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_reverse_http_error(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await budget_interface.reverse(vlab_id, project_id, 100.0)

    assert exc_info.value.type == AccountingErrorValue.REVERSE_PROJECT_BUDGET_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_move_http_error(
    budget_interface: BudgetInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    from_project = uuid4()
    to_project = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await budget_interface.move(vlab_id, from_project, to_project, 100.0)

    assert exc_info.value.type == AccountingErrorValue.MOVE_PROJECT_BUDGET_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST
