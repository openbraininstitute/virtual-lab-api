from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from virtual_labs.external.accounting.models import (
    ProjectReportsResponse,
    VirtualLabReportsResponse,
)
from virtual_labs.usecases.accounting import (
    get_project_reports,
    get_virtual_lab_reports,
)


@pytest.mark.asyncio
async def test_get_virtual_lab_reports() -> None:
    virtual_lab_id = uuid4()
    mock_response_data = {
        "message": f"Job report for virtual-lab {virtual_lab_id}",
        "data": {
            "items": [
                {
                    "job_id": str(uuid4()),
                    "user_id": str(uuid4()),
                    "name": None,
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
                "self": f"http://accounting.local/report/virtual-lab/{virtual_lab_id}?page=1&page_size=1000",
                "prev": None,
                "next": None,
                "first": f"http://accounting.local/report/virtual-lab/{virtual_lab_id}?page_size=1000&page=1",
                "last": f"http://accounting.local/report/virtual-lab/{virtual_lab_id}?page_size=1000&page=1",
            },
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
        client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await get_virtual_lab_reports(virtual_lab_id, page=1, page_size=10)

        assert isinstance(result, VirtualLabReportsResponse)
        assert len(result.data.items) == 1
        assert result.data.meta.page == 1
        assert result.data.meta.page_size == 10


@pytest.mark.asyncio
async def test_get_project_reports() -> None:
    project_id = uuid4()
    mock_response_data = {
        "message": f"Job report for project {project_id}",
        "data": {
            "items": [
                {
                    "job_id": str(uuid4()),
                    "user_id": str(uuid4()),
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
                "self": f"http://accounting.local/report/project/{project_id}?page=1&page_size=1000",
                "prev": None,
                "next": None,
                "first": f"http://accounting.local/report/project/{project_id}?page_size=1000&page=1",
                "last": f"http://accounting.local/report/project/{project_id}?page_size=1000&page=1",
            },
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
        client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await get_project_reports(project_id, page=1, page_size=10)

        assert isinstance(result, ProjectReportsResponse)
        assert len(result.data.items) == 1
        assert result.data.meta.page == 1
        assert result.data.meta.page_size == 10
