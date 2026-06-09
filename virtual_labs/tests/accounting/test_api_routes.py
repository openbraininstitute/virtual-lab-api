from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.tests.utils import (
    cleanup_resources,
    get_headers,
)


@pytest_asyncio.fixture
async def mock_lab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, str, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()

    lab_response = await client.post("/virtual-labs", json=body, headers=headers)
    lab_id = lab_response.json()["id"]

    project_body = {"name": f"Test Project {uuid4()}", "description": "Test"}
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    project_id = project_response.json()["id"]

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
        "virtual_labs.usecases.accounting.get_virtual_lab_balance"
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

    with patch("virtual_labs.usecases.accounting.get_project_balance") as mock_balance:
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
                    "user_id": str(uuid4()),
                    "proj_id": str(proj_id),
                    "name": None,
                    "type": "oneshot",
                    "subtype": "ml-llm",
                    "reserved_at": "2025-01-10T10:12:03Z",
                    "started_at": "2025-01-10T10:12:04Z",
                    "amount": "39.2",
                    "count": 39,
                    "reserved_amount": "24.2",
                    "reserved_count": 24,
                    "duration": None,
                    "reserved_duration": None,
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
        "virtual_labs.usecases.accounting.get_virtual_lab_reports"
    ) as mock_reports:
        mock_reports.return_value = mock_reports_response

        response = await client.get(
            f"/virtual-labs/{lab_id}/accounting/reports",
            headers=headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        assert response.json() == mock_reports_response


@pytest.mark.asyncio
async def test_assign_project_budget(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    client, lab_id, project_id, headers = mock_lab_with_project

    mock_assign_response = {"message": "Assign budget operation executed", "data": None}

    with patch("virtual_labs.usecases.accounting.assign_project_budget") as mock_assign:
        mock_assign.return_value = mock_assign_response

        response = await client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/budget/assign",
            headers=headers,
            json={"amount": 200.00},
        )

        assert response.status_code == 200
        assert response.json() == mock_assign_response


@pytest.mark.asyncio
async def test_reverse_project_budget(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    client, lab_id, project_id, headers = mock_lab_with_project

    mock_reverse_response = {
        "message": "Reverse budget operation executed",
        "data": None,
    }

    with patch(
        "virtual_labs.usecases.accounting.reverse_project_budget"
    ) as mock_reverse:
        mock_reverse.return_value = mock_reverse_response

        response = await client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/budget/reverse",
            headers=headers,
            json={"amount": 500.00},
        )

        assert response.status_code == 200
        assert response.json() == mock_reverse_response


@pytest.fixture
def vlab_with_course():
    """Patch get_undeleted_virtual_lab to return a vlab that has a course."""
    mock_vlab = MagicMock()
    mock_vlab.course = MagicMock()  # truthy → vlab has a course
    with patch(
        "virtual_labs.routes.accounting.get_undeleted_virtual_lab",
        new_callable=AsyncMock,
        return_value=mock_vlab,
    ):
        yield mock_vlab


@pytest.fixture
def service_admin_auth(vlab_with_course):
    """Activates vlab_with_course and provides service admin headers."""
    yield get_headers("test-service-admin")


@pytest.mark.asyncio
async def test_reverse_project_budget_fails_if_vlab_has_course(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
    vlab_with_course,
) -> None:
    """Caller IS a vlab admin (owns the lab) but is NOT a service admin.
    Course restriction must still block the operation."""
    client, lab_id, project_id, headers = mock_lab_with_project

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/budget/reverse",
        headers=headers,
        json={"amount": 500.00},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reverse_project_budget_works_if_vlab_has_course_and_caller_is_service_admin(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
    service_admin_auth,
) -> None:
    client, lab_id, project_id, _ = mock_lab_with_project
    headers = service_admin_auth

    mock_reverse_response = {
        "message": "Reverse budget operation executed",
        "data": None,
    }

    with patch(
        "virtual_labs.usecases.accounting.reverse_project_budget"
    ) as mock_reverse:
        mock_reverse.return_value = mock_reverse_response

        response = await client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/budget/reverse",
            headers=headers,
            json={"amount": 500.00},
        )

        assert response.status_code == 200
        assert response.json() == mock_reverse_response


@pytest.mark.asyncio
async def test_assign_project_budget_fails_if_vlab_has_course(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
    vlab_with_course,
) -> None:
    """Caller IS a vlab admin (owns the lab) but is NOT a service admin.
    Course restriction must still block the operation."""
    client, lab_id, project_id, headers = mock_lab_with_project

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/budget/assign",
        headers=headers,
        json={"amount": 200.00},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assign_project_budget_works_if_vlab_has_course_and_caller_is_service_admin(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
    service_admin_auth,
) -> None:
    client, lab_id, project_id, _ = mock_lab_with_project
    headers = service_admin_auth

    mock_assign_response = {"message": "Assign budget operation executed", "data": None}

    with patch("virtual_labs.usecases.accounting.assign_project_budget") as mock_assign:
        mock_assign.return_value = mock_assign_response

        response = await client.post(
            f"/virtual-labs/{lab_id}/projects/{project_id}/accounting/budget/assign",
            headers=headers,
            json={"amount": 200.00},
        )

        assert response.status_code == 200
        assert response.json() == mock_assign_response


# ──────────────────────────────────────────────────────────────────────
# Top-up endpoint tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_top_up_virtual_lab_budget_fails_if_not_service_admin(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    """Regular vlab admin cannot top up — only service admins can."""
    client, lab_id, _, headers = mock_lab_with_project

    response = await client.post(
        f"/virtual-labs/{lab_id}/accounting/budget/top-up",
        headers=headers,
        json={"amount": 1000.00},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_top_up_virtual_lab_budget_works_for_service_admin(
    mock_lab_with_project: tuple[AsyncClient, str, str, dict[str, str]],
) -> None:
    client, lab_id, _, _ = mock_lab_with_project
    headers = get_headers("test-service-admin")

    mock_top_up_response = {"message": "Top up operation executed", "data": None}

    with patch(
        "virtual_labs.usecases.accounting.top_up_virtual_lab_budget"
    ) as mock_top_up:
        mock_top_up.return_value = mock_top_up_response

        response = await client.post(
            f"/virtual-labs/{lab_id}/accounting/budget/top-up",
            headers=headers,
            json={"amount": 1000.00},
        )

        assert response.status_code == 200
        assert response.json() == mock_top_up_response
