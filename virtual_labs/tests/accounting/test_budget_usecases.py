from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from virtual_labs.external.accounting.models import (
    BudgetAssignResponse,
    BudgetMoveResponse,
    BudgetReverseResponse,
    BudgetTopUpResponse,
)
from virtual_labs.usecases.accounting import (
    assign_project_budget,
    move_project_budget,
    reverse_project_budget,
    top_up_virtual_lab_budget,
)


@pytest.mark.asyncio
async def test_top_up() -> None:
    vlab_id = uuid4()
    amount = 100.0
    mock_response_data = {"message": "Top-up operation executed", "data": None}

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

        result = await top_up_virtual_lab_budget(vlab_id, amount)

        assert isinstance(result, BudgetTopUpResponse)


@pytest.mark.asyncio
async def test_assign() -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    amount = 50.0
    mock_response_data = {
        "message": "Assign budget operation executed",
        "data": None,
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

        result = await assign_project_budget(vlab_id, project_id, amount)

        assert isinstance(result, BudgetAssignResponse)


@pytest.mark.asyncio
async def test_reverse() -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    amount = 25.0
    mock_response_data = {
        "message": "Reverse budget operation executed",
        "data": None,
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

        result = await reverse_project_budget(vlab_id, project_id, amount)

        assert isinstance(result, BudgetReverseResponse)


@pytest.mark.asyncio
async def test_move() -> None:
    vlab_id = uuid4()
    debited_from = uuid4()
    credited_to = uuid4()
    amount = 75.0
    mock_response_data = {
        "message": "Move budget operation executed",
        "data": None,
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

        result = await move_project_budget(vlab_id, debited_from, credited_to, amount)

        assert isinstance(result, BudgetMoveResponse)
