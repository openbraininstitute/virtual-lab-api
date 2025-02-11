from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, HTTPStatusError, Response

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.models import (
    ProjectReportsResponse,
    VirtualLabReportsResponse,
)
from virtual_labs.external.accounting.report_interface import ReportInterface
from virtual_labs.infrastructure.settings import settings


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock(spec=AsyncClient)


@pytest.fixture
def report_interface(mock_client: AsyncMock) -> ReportInterface:
    return ReportInterface(client=mock_client, client_token="test-token")


@pytest.mark.asyncio
async def test_api_url(report_interface: ReportInterface) -> None:
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/report"
    assert report_interface._api_url == expected_url


@pytest.mark.asyncio
async def test_get_virtual_lab_reports_success(
    report_interface: ReportInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": f"Job report for virtual-lab {vlab_id}",
        "data": {
            "items": [
                {
                    "job_id": str(uuid4()),
                    "proj_id": str(uuid4()),
                    "type": "oneshot",
                    "subtype": "ml-llm",
                    "reserved_at": "2025-01-10T10:12:03Z",
                    "started_at": "2025-01-10T10:12:04Z",
                    "amount": "39.2",
                    "count": 39,
                    "reserved_amount": "24.2",
                    "reserved_count": 24,
                }
            ],
            "meta": {
                "page": 1,
                "page_size": 10,
                "total_pages": 1,
                "total_items": 1,
            },
            "links": {
                "self": f"http://accounting.local/report/virtual-lab/{vlab_id}?page=1&page_size=1000",
                "prev": None,
                "next": None,
                "first": f"http://accounting.local/report/virtual-lab/{vlab_id}?page_size=1000&page=1",
                "last": f"http://accounting.local/report/virtual-lab/{vlab_id}?page_size=1000&page=1",
            },
        },
    }
    mock_client.get.return_value = mock_response

    result = await report_interface.get_virtual_lab_reports(
        vlab_id, page=1, page_size=10
    )

    # Check if the method was called once
    mock_client.get.assert_called_once()

    # Get the call arguments
    call_args = mock_client.get.call_args[0]
    call_kwargs = mock_client.get.call_args[1]

    # Check URL
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/report/virtual-lab/{vlab_id}"
    assert call_args[0] == expected_url

    # Check headers
    expected_headers = {
        "Content-Type": "application/json",
        "Authorization": "bearer test-token",
    }
    assert call_kwargs["headers"] == expected_headers

    # Check query parameters
    expected_params = {"page": 1, "page_size": 10}
    assert call_kwargs["params"] == expected_params

    assert isinstance(result, VirtualLabReportsResponse)
    assert len(result.data.items) == 1


@pytest.mark.asyncio
async def test_get_project_reports_success(
    report_interface: ReportInterface, mock_client: AsyncMock
) -> None:
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.json.return_value = {
        "message": f"Job report for project {project_id}",
        "data": {
            "items": [
                {
                    "job_id": str(uuid4()),
                    "type": "oneshot",
                    "subtype": "ml-llm",
                    "reserved_at": "2025-01-10T10:12:03Z",
                    "started_at": "2025-01-10T10:12:04Z",
                    "amount": "39.2",
                    "count": 39,
                    "reserved_amount": "24.2",
                    "reserved_count": 24,
                }
            ],
            "meta": {
                "page": 1,
                "page_size": 10,
                "total_pages": 1,
                "total_items": 1,
            },
            "links": {
                "self": f"http://accounting.local/report/project/{project_id}?page=1&page_size=1000",
                "prev": None,
                "next": None,
                "first": f"http://accounting.local/report/project/{project_id}?page_size=1000&page=1",
                "last": f"http://accounting.local/report/project/{project_id}?page_size=1000&page=1",
            },
        },
    }
    mock_client.get.return_value = mock_response

    result = await report_interface.get_project_reports(
        project_id, page=1, page_size=10
    )

    # Check if the method was called once
    mock_client.get.assert_called_once()

    # Get the call arguments
    call_args = mock_client.get.call_args[0]
    call_kwargs = mock_client.get.call_args[1]

    # Check URL
    expected_url = f"{settings.ACCOUNTING_BASE_URL}/report/project/{project_id}"
    assert call_args[0] == expected_url

    # Check query parameters
    expected_params = {"page": 1, "page_size": 10}
    assert call_kwargs["params"] == expected_params

    assert isinstance(result, ProjectReportsResponse)
    assert len(result.data.items) == 1


@pytest.mark.asyncio
async def test_get_virtual_lab_reports_http_error(
    report_interface: ReportInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.get.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await report_interface.get_virtual_lab_reports(vlab_id, page=1, page_size=10)

    assert exc_info.value.type == AccountingErrorValue.FETCH_VIRTUAL_LAB_REPORTS_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_get_project_reports_http_error(
    report_interface: ReportInterface, mock_client: AsyncMock
) -> None:
    project_id = uuid4()
    mock_response = Mock(spec=Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "test error"}

    error_response = HTTPStatusError("Error", request=Mock(), response=mock_response)
    mock_client.get.side_effect = error_response

    with pytest.raises(AccountingError) as exc_info:
        await report_interface.get_project_reports(project_id, page=1, page_size=10)

    assert exc_info.value.type == AccountingErrorValue.FETCH_PROJECT_REPORTS_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_get_virtual_lab_reports_general_error(
    report_interface: ReportInterface, mock_client: AsyncMock
) -> None:
    vlab_id = uuid4()
    mock_client.get.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await report_interface.get_virtual_lab_reports(vlab_id, page=1, page_size=10)

    assert exc_info.value.type == AccountingErrorValue.FETCH_VIRTUAL_LAB_REPORTS_ERROR


@pytest.mark.asyncio
async def test_get_project_reports_general_error(
    report_interface: ReportInterface, mock_client: AsyncMock
) -> None:
    project_id = uuid4()
    mock_client.get.side_effect = Exception("General error")

    with pytest.raises(AccountingError) as exc_info:
        await report_interface.get_project_reports(project_id, page=1, page_size=10)

    assert exc_info.value.type == AccountingErrorValue.FETCH_PROJECT_REPORTS_ERROR
