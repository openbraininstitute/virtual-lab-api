"""
Tests for workspace hierarchy species preference endpoints.

- GET /users/preferences/workspace-hierarchy-species
- PATCH /users/preferences/workspace-hierarchy-species
"""

from http import HTTPStatus
from typing import Any, Dict
from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestGetWorkspaceHierarchySpeciesPreference:
    """Test cases for GET /users/preferences/workspace-hierarchy-species endpoint."""

    @pytest.mark.asyncio
    async def test_get_preference_when_none_set(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test getting preference when no preference is set."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        response = await client.get(
            "/users/preferences/workspace-hierarchy-species",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert (
            response_data["message"]
            == "Workspace hierarchy species preference retrieved"
        )
        assert response_data["data"]["preference"] is None

    @pytest.mark.asyncio
    async def test_get_preference_after_setting(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test getting preference after it has been set."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        hierarchy_id = str(uuid4())
        brain_region_id = str(uuid4())
        payload = {
            "hierarchy_id": hierarchy_id,
            "species_name": "Mus musculus",
            "brain_region_id": brain_region_id,
            "brain_region_name": "Primary Visual Cortex",
        }

        await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        response = await client.get(
            "/users/preferences/workspace-hierarchy-species",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        preference = response_data["data"]["preference"]
        assert preference["hierarchy_id"] == hierarchy_id
        assert preference["species_name"] == "Mus musculus"
        assert preference["brain_region_id"] == brain_region_id
        assert preference["brain_region_name"] == "Primary Visual Cortex"
        assert preference["species_selection_mode"] == "focused"


class TestUpdateWorkspaceHierarchySpeciesPreference:
    """Test cases for PATCH /users/preferences/workspace-hierarchy-species endpoint."""

    @pytest.mark.asyncio
    async def test_create_preference_with_all_fields(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test creating preference with all fields populated."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        hierarchy_id = str(uuid4())
        brain_region_id = str(uuid4())
        payload = {
            "hierarchy_id": hierarchy_id,
            "species_name": "Homo sapiens",
            "brain_region_id": brain_region_id,
            "brain_region_name": "Hippocampus",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert (
            response_data["message"] == "Workspace hierarchy species preference updated"
        )
        preference = response_data["data"]["preference"]
        assert preference["hierarchy_id"] == hierarchy_id
        assert preference["species_name"] == "Homo sapiens"
        assert preference["brain_region_id"] == brain_region_id
        assert preference["brain_region_name"] == "Hippocampus"
        assert preference["species_selection_mode"] == "focused"
        assert response_data["data"]["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_create_preference_with_required_fields_only(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test creating preference with only required fields."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        hierarchy_id = str(uuid4())
        payload = {
            "hierarchy_id": hierarchy_id,
            "species_name": "Mus musculus",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        preference = response_data["data"]["preference"]
        assert preference["hierarchy_id"] == hierarchy_id
        assert preference["species_name"] == "Mus musculus"
        assert preference["brain_region_id"] is None
        assert preference["brain_region_name"] is None
        assert preference["species_selection_mode"] == "focused"

    @pytest.mark.asyncio
    async def test_update_existing_preference(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test updating an existing preference."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # Create initial preference
        initial_hierarchy_id = str(uuid4())
        initial_payload = {
            "hierarchy_id": initial_hierarchy_id,
            "species_name": "Homo sapiens",
            "brain_region_id": str(uuid4()),
            "brain_region_name": "Cortex",
        }

        await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=initial_payload,
            headers=headers,
        )

        # Update with new values
        updated_hierarchy_id = str(uuid4())
        updated_brain_region_id = str(uuid4())
        updated_payload = {
            "hierarchy_id": updated_hierarchy_id,
            "species_name": "Mus musculus",
            "brain_region_id": updated_brain_region_id,
            "brain_region_name": "Thalamus",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=updated_payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        preference = response_data["data"]["preference"]
        assert preference["hierarchy_id"] == updated_hierarchy_id
        assert preference["species_name"] == "Mus musculus"
        assert preference["brain_region_id"] == updated_brain_region_id
        assert preference["brain_region_name"] == "Thalamus"
        assert preference["species_selection_mode"] == "focused"

    @pytest.mark.asyncio
    async def test_update_preference_clear_optional_fields(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test updating preference to clear optional fields."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # Create initial preference with all fields
        hierarchy_id = str(uuid4())
        initial_payload = {
            "hierarchy_id": hierarchy_id,
            "species_name": "Homo sapiens",
            "brain_region_id": str(uuid4()),
            "brain_region_name": "Hippocampus",
        }

        await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=initial_payload,
            headers=headers,
        )

        # Update with only required fields (clearing optional)
        new_hierarchy_id = str(uuid4())
        updated_payload = {
            "hierarchy_id": new_hierarchy_id,
            "species_name": "Mus musculus",
            "brain_region_id": None,
            "brain_region_name": None,
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=updated_payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        preference = response_data["data"]["preference"]
        assert preference["hierarchy_id"] == new_hierarchy_id
        assert preference["brain_region_id"] is None
        assert preference["brain_region_name"] is None
        assert preference["species_selection_mode"] == "focused"

    @pytest.mark.asyncio
    async def test_create_preference_with_all_species_mode(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test creating preference with species_selection_mode='all'."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "species_selection_mode": "all",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        preference = response_data["data"]["preference"]
        assert preference["species_selection_mode"] == "all"
        assert preference["hierarchy_id"] is None
        assert preference["species_name"] is None
        assert preference["brain_region_id"] is None
        assert preference["brain_region_name"] is None

    @pytest.mark.asyncio
    async def test_switch_from_focused_to_all_mode(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test switching from focused mode to all mode clears id/name fields."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # First set a focused preference
        focused_payload = {
            "hierarchy_id": str(uuid4()),
            "species_name": "Homo sapiens",
            "brain_region_id": str(uuid4()),
            "brain_region_name": "Cortex",
            "species_selection_mode": "focused",
        }
        await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=focused_payload,
            headers=headers,
        )

        # Switch to all mode
        all_payload = {
            "species_selection_mode": "all",
        }
        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=all_payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        preference = response.json()["data"]["preference"]
        assert preference["species_selection_mode"] == "all"
        assert preference["hierarchy_id"] is None
        assert preference["species_name"] is None
        assert preference["brain_region_id"] is None
        assert preference["brain_region_name"] is None

    @pytest.mark.asyncio
    async def test_switch_from_all_to_focused_mode(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test switching from all mode back to focused mode."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # First set all mode
        await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json={"species_selection_mode": "all"},
            headers=headers,
        )

        # Switch back to focused
        hierarchy_id = str(uuid4())
        focused_payload = {
            "hierarchy_id": hierarchy_id,
            "species_name": "Mus musculus",
            "species_selection_mode": "focused",
        }
        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=focused_payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        preference = response.json()["data"]["preference"]
        assert preference["species_selection_mode"] == "focused"
        assert preference["hierarchy_id"] == hierarchy_id
        assert preference["species_name"] == "Mus musculus"

    @pytest.mark.asyncio
    async def test_get_preference_after_setting_all_mode(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test GET returns correct data after setting all mode."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json={"species_selection_mode": "all"},
            headers=headers,
        )

        response = await client.get(
            "/users/preferences/workspace-hierarchy-species",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        preference = response.json()["data"]["preference"]
        assert preference["species_selection_mode"] == "all"
        assert preference["hierarchy_id"] is None
        assert preference["species_name"] is None


class TestWorkspaceHierarchySpeciesValidation:
    """Test validation for workspace hierarchy species preference endpoints."""

    @pytest.mark.asyncio
    async def test_missing_required_field_hierarchy_id(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when hierarchy_id is missing."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "species_name": "Homo sapiens",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_missing_required_field_species_name(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when species_name is missing."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "hierarchy_id": str(uuid4()),
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_invalid_hierarchy_id_format(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when hierarchy_id is not a valid UUID."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "hierarchy_id": "not-a-valid-uuid",
            "species_name": "Homo sapiens",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_empty_species_name(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when species_name is empty."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "hierarchy_id": str(uuid4()),
            "species_name": "",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_invalid_species_selection_mode(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when species_selection_mode is invalid."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "hierarchy_id": str(uuid4()),
            "species_name": "Homo sapiens",
            "species_selection_mode": "invalid_mode",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_focused_mode_missing_hierarchy_id(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when focused mode is explicitly set but hierarchy_id is missing."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "species_name": "Homo sapiens",
            "species_selection_mode": "focused",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_focused_mode_missing_species_name(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test validation error when focused mode is explicitly set but species_name is missing."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "hierarchy_id": str(uuid4()),
            "species_selection_mode": "focused",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_all_mode_ignores_provided_ids(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test that 'all' mode coerces id/name fields to None even if provided."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "hierarchy_id": str(uuid4()),
            "species_name": "Homo sapiens",
            "brain_region_id": str(uuid4()),
            "brain_region_name": "Cortex",
            "species_selection_mode": "all",
        }

        response = await client.patch(
            "/users/preferences/workspace-hierarchy-species",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        preference = response.json()["data"]["preference"]
        assert preference["species_selection_mode"] == "all"
        assert preference["hierarchy_id"] is None
        assert preference["species_name"] is None
        assert preference["brain_region_id"] is None
        assert preference["brain_region_name"] is None
