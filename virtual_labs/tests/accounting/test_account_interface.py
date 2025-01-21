from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, HTTPStatusError, Response

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.account_interface import AccountInterface
from virtual_labs.external.accounting.models import (
    ProjAccountCreationResponse,
    VlabAccountCreationResponse,
)
from virtual_labs.infrastructure.settings import settings


@pytest.fixture
def mock_client():
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def account_interface(mock_client):
    return AccountInterface(client=mock_client, client_token="test-token")


@pytest.mark.asyncio
async def test_api_url(account_interface):
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/account"
    assert account_interface._api_url == expected_url


@pytest.mark.asyncio
async def test_create_virtual_lab_account_success(account_interface, mock_client):
    vlab_id = uuid4()
    vlab_name = "test-vlab"
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Virtual lab created",
        "data": {
            "id": str(vlab_id),
            "name": vlab_name,
        },
    }
    mock_client.post.return_value = mock_response

    result = await account_interface.create_virtual_lab_account(vlab_id, vlab_name)

    assert isinstance(result, VlabAccountCreationResponse)
    assert result.data.id == vlab_id

    mock_client.post.assert_called_once()

    expected_url = f"{settings.ACCOUNTING_BASE_URL}/account/virtual-lab"
    assert mock_client.post.call_args[0][0] == expected_url


@pytest.mark.asyncio
async def test_create_virtual_lab_account_http_error(account_interface, mock_client):
    vlab_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await account_interface.create_virtual_lab_account(vlab_id, "test-vlab")

    assert exc_info.value.type == AccountingErrorValue.CREATE_VIRTUAL_LAB_ACCOUNT_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_create_virtual_lab_account_general_error(account_interface, mock_client):
    virtual_lab_id = uuid4()
    mock_client.post.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await account_interface.create_virtual_lab_account(virtual_lab_id, "test-vlab")

    assert exc_info.value.type == AccountingErrorValue.CREATE_VIRTUAL_LAB_ACCOUNT_ERROR
    assert exc_info.value.http_status_code is None


@pytest.mark.asyncio
async def test_create_project_account_success(account_interface, mock_client):
    virtual_lab_id = uuid4()
    project_id = uuid4()
    proj_name = "test-project"
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": "Project created",
        "data": {
            "id": str(project_id),
            "name": proj_name,
        },
    }
    mock_client.post.return_value = mock_response

    result = await account_interface.create_project_account(
        virtual_lab_id, project_id, proj_name
    )

    assert isinstance(result, ProjAccountCreationResponse)
    assert result.data.id == project_id

    mock_client.post.assert_called_once()

    expected_url = f"{settings.ACCOUNTING_BASE_URL}/account/project"
    assert mock_client.post.call_args[0][0] == expected_url


@pytest.mark.asyncio
async def test_create_project_account_http_error(account_interface, mock_client):
    virtual_lab_id = uuid4()
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.post.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await account_interface.create_project_account(
            virtual_lab_id, project_id, "test-name"
        )

    assert exc_info.value.type == AccountingErrorValue.CREATE_PROJECT_ACCOUNT_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_create_project_account_general_error(account_interface, mock_client):
    virtual_lab_id = uuid4()
    project_id = uuid4()
    mock_client.post.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await account_interface.create_project_account(
            virtual_lab_id, project_id, "test-name"
        )

    assert exc_info.value.type == AccountingErrorValue.CREATE_PROJECT_ACCOUNT_ERROR
    assert exc_info.value.http_status_code is None
