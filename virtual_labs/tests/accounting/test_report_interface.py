from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import AsyncClient, HTTPStatusError, Response
from obp_accounting_sdk.constants import ServiceSubtype, ServiceType  # type: ignore[import-untyped]

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.interfaces.report_interface import ReportInterface
from virtual_labs.external.accounting.models import (
    ProjectReportsResponse,
    VirtualLabReportsResponse,
)
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
                    "user_id": str(uuid4()),
                    "proj_id": str(uuid4()),
                    "type": ServiceType.ONESHOT,
                    "subtype": ServiceSubtype.ML_LLM,
                    "reserved_at": "2025-01-10T10:12:03Z",
                    "started_at": "2025-01-10T10:12:04Z",
                    "amount": "39.2",
                    "count": 39,
                    "reserved_amount": "24.2",
                    "reserved_count": 24,
                },
                {
                    "job_id": str(uuid4()),
                    "user_id": str(uuid4()),
                    "name": "LFPy: active single cell model IClamp",
                    "proj_id": str(uuid4()),
                    "type": ServiceType.LONGRUN,
                    "subtype": ServiceSubtype.NOTEBOOK,
                    "reserved_at": "2025-09-08T08:37:36.807277Z",
                    "started_at": "2025-09-08T08:37:38Z",
                    "finished_at": "2025-09-08T13:55:13.342013Z",
                    "cancelled_at": "2025-09-08T13:55:13.342013Z",
                    "amount": "315.9810",
                    "duration": 19055,
                    "reserved_amount": "0.0166",
                    "reserved_duration": 1,
                },
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
    assert len(result.data.items) == 2
    # first item is 'oneshot'
    assert result.data.items[0].count == 39
    assert result.data.items[0].duration is None
    # second item is 'longrun'
    assert result.data.items[1].count is None
    assert result.data.items[1].duration == 19055


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
                    "user_id": str(uuid4()),
                    "type": ServiceType.ONESHOT,
                    "subtype": ServiceSubtype.ML_LLM,
                    "reserved_at": "2025-01-10T10:12:03Z",
                    "started_at": "2025-01-10T10:12:04Z",
                    "amount": "39.2",
                    "count": 39,
                    "reserved_amount": "24.2",
                    "reserved_count": 24,
                },
                {
                    "job_id": str(uuid4()),
                    "user_id": str(uuid4()),
                    "name": "Model parameter comparison plot",
                    "type": ServiceType.LONGRUN,
                    "subtype": ServiceSubtype.NOTEBOOK,
                    "reserved_at": "2025-09-08T08:38:40.172405Z",
                    "started_at": "2025-09-08T08:38:42Z",
                    "finished_at": "2025-09-08T13:55:13.342013Z",
                    "cancelled_at": "2025-09-08T13:55:13.342013Z",
                    "amount": "314.9186",
                    "duration": 18991,
                    "reserved_amount": "0.0166",
                    "reserved_duration": 1,
                },
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
    assert len(result.data.items) == 2
    # first item is 'oneshot'
    assert result.data.items[0].count == 39
    assert result.data.items[0].duration is None
    # second item is 'longrun'
    assert result.data.items[1].count is None
    assert result.data.items[1].duration == 18991


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
