from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, str, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "plan_id": 1,
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()

    lab_response = await client.post("/virtual-labs", json=body, headers=headers)
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    project_body = {"name": f"Test Project {uuid4()}", "description": "Test"}
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    project_id = project_response.json()["data"]["project"]["id"]

    yield client, lab_id, project_id, headers
    await cleanup_resources(client=client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_get_virtual_lab_balance(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    client, lab_id, proj_id, headers = mock_lab_with_project

    mock_balance_response = {
        "message": "Balance for virtual-lab including projects",
        "data": {
            "vlab_id": str(lab_id),
            "balance": "1000",
            "projects": [
                {
                    "proj_id": str(proj_id),
                    "balance": "9763.40",
                    "reservation": "0.00",
                }
            ],
        },
    }

    with patch(
        "virtual_labs.external.accounting.balance.get_virtual_lab_balance"
    ) as mock_balance:
        mock_balance.return_value = mock_balance_response

        response = await client.get(
            f"/virtual-labs/{lab_id}/accounting/balance",
            headers=headers,
            params={"include_projects": True},
        )

        assert response.status_code == 200
        assert response.json() == mock_balance_response


@pytest.mark.asyncio
async def test_get_project_balance(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    client, lab_id, project_id, headers = mock_lab_with_project

    mock_balance_response = {
        "message": "Balance for project",
        "data": {"proj_id": str(project_id), "balance": "100", "reservation": "15.20"},
    }

    with patch(
        "virtual_labs.external.accounting.balance.get_project_balance"
    ) as mock_balance:
        mock_balance.return_value = mock_balance_response

        response = await client.get(
            f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/balance",
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json() == mock_balance_response


@pytest.mark.asyncio
async def test_get_virtual_lab_reports(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    client, lab_id, proj_id, headers = mock_lab_with_project

    mock_reports_response = {
        "message": f"Job report for virtual-lab {lab_id}",
        "data": {
            "items": [
                {
                    "job_id": str(uuid4()),
                    "proj_id": str(proj_id),
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
                "self": f"http://accounting.local/report/virtual-lab/{lab_id}?page=1&page_size=1000",
                "prev": None,
                "next": None,
                "first": f"http://accounting.local/report/virtual-lab/{lab_id}?page_size=1000&page=1",
                "last": f"http://accounting.local/report/virtual-lab/{lab_id}?page_size=1000&page=1",
            },
        },
    }

    with patch(
        "virtual_labs.external.accounting.report.get_virtual_lab_reports"
    ) as mock_reports:
        mock_reports.return_value = mock_reports_response

        response = await client.get(
            f"/virtual-labs/{lab_id}/accounting/reports",
            headers=headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        assert response.json() == mock_reports_response
