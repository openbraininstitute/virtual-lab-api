from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from virtual_labs.external.accounting.models import (
    ProjAccountCreationResponse,
    VlabAccountCreationResponse,
)
from virtual_labs.usecases.accounting import (
    create_project_account,
    create_virtual_lab_account,
)


@pytest.mark.asyncio
async def test_create_virtual_lab_account() -> None:
    vlab_id = uuid4()
    vlab_name = "test-vlab"
    mock_response_data = {
        "message": "Virtual lab created",
        "data": {
            "id": str(vlab_id),
            "name": vlab_name,
        },
    }

    with (
        patch("httpx.AsyncClient") as mock_client,
        patch("virtual_labs.infrastructure.kc.auth.get_client_token") as mock_token,
    ):
        mock_token.return_value = "test-token"

        mock_response = AsyncMock()
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None

        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await create_virtual_lab_account(vlab_id, vlab_name)

        assert isinstance(result, VlabAccountCreationResponse)
        assert result.data.id == vlab_id
        assert result.data.name == vlab_name


@pytest.mark.asyncio
async def test_create_virtual_lab_account_with_initial_balance() -> None:
    vlab_id = uuid4()
    vlab_name = "test-vlab"
    mock_response_data = {
        "message": "Virtual lab created",
        "data": {
            "id": str(vlab_id),
            "name": vlab_name,
        },
    }

    with (
        patch("httpx.AsyncClient") as mock_client,
        patch("virtual_labs.infrastructure.kc.auth.get_client_token") as mock_token,
    ):
        mock_token.return_value = "test-token"

        mock_response = AsyncMock()
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None

        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await create_virtual_lab_account(vlab_id, vlab_name, Decimal(100))

        assert isinstance(result, VlabAccountCreationResponse)
        assert result.data.id == vlab_id
        assert result.data.name == vlab_name


@pytest.mark.asyncio
async def test_create_project_account() -> None:
    vlab_id = uuid4()
    project_id = uuid4()
    project_name = "test-project"
    mock_response_data = {
        "message": "Project created",
        "data": {
            "id": str(project_id),
            "name": project_name,
        },
    }

    with (
        patch("httpx.AsyncClient") as mock_client,
        patch("virtual_labs.infrastructure.kc.auth.get_client_token") as mock_token,
    ):
        mock_token.return_value = "test-token"

        mock_response = AsyncMock()
        mock_response.json = lambda: mock_response_data
        mock_response.raise_for_status = lambda: None

        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance

        result = await create_project_account(vlab_id, project_id, project_name)

        assert isinstance(result, ProjAccountCreationResponse)
        assert result.data.id == project_id
        assert result.data.name == project_name
