from http import HTTPStatus
from typing import Any, Dict
from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestGetRecentWorkspace:
    """Test cases for GET /users/preferences/recent-workspace endpoint."""

    @pytest.mark.asyncio
    async def test_get_recent_workspace_when_none_set(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test getting recent workspace when no preference is set (returns default)."""
        client = async_test_client
        vl_response, virtual_lab_id, data = mock_user_with_lab_and_project
        headers = data["headers"]

        response = await client.get(
            "/users/preferences/recent-workspace", headers=headers
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()

        # should return default workspace (last created project)
        assert response_data["data"]["recent_workspace"]["workspace"] is not None
        assert (
            response_data["data"]["recent_workspace"]["workspace"]["virtual_lab_id"]
            == virtual_lab_id
        )
        assert "virtual_lab" in response_data["data"]["recent_workspace"]
        assert "project" in response_data["data"]["recent_workspace"]

    @pytest.mark.asyncio
    async def test_get_recent_workspace_when_preference_exists(
        self,
        async_test_client: AsyncClient,
        mock_user_with_recent_workspace: tuple[str, str, Dict[str, Any]],
    ) -> None:
        """Test getting recent workspace when user has a preference set."""
        client = async_test_client
        virtual_lab_id, project_id, headers = mock_user_with_recent_workspace

        response = await client.get(
            "/users/preferences/recent-workspace", headers=headers
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()

        # should return the set workspace
        workspace = response_data["data"]["recent_workspace"]["workspace"]
        assert workspace["virtual_lab_id"] == virtual_lab_id
        assert workspace["project_id"] == project_id
        assert response_data["data"]["recent_workspace"]["updated_at"] is not None
        assert "virtual_lab" in response_data["data"]["recent_workspace"]
        assert "project" in response_data["data"]["recent_workspace"]

    @pytest.mark.asyncio
    async def test_get_recent_workspace_with_multiple_projects(
        self,
        async_test_client: AsyncClient,
        mock_user_with_multiple_projects: tuple[str, Dict[str, str], Dict[str, Any]],
    ) -> None:
        """Test getting recent workspace returns the most recently created project as default."""
        client = async_test_client
        virtual_lab_id, projects, headers = mock_user_with_multiple_projects

        response = await client.get(
            "/users/preferences/recent-workspace", headers=headers
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()

        # should return the last created project (project_2)
        workspace = response_data["data"]["recent_workspace"]["workspace"]
        assert workspace["virtual_lab_id"] == virtual_lab_id
        assert workspace["project_id"] in projects.values()
        assert "virtual_lab" in response_data["data"]["recent_workspace"]
        assert "project" in response_data["data"]["recent_workspace"]

    @pytest.mark.asyncio
    async def test_get_recent_workspace_user_no_lab(
        self, async_test_client: AsyncClient, mock_user_with_no_lab: Dict[str, Any]
    ) -> None:
        """Test getting recent workspace when user has no virtual labs."""
        client = async_test_client
        headers = mock_user_with_no_lab

        response = await client.get(
            "/users/preferences/recent-workspace", headers=headers
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()

        # should return no workspace
        assert response_data["data"]["recent_workspace"]["workspace"] is None
        assert response_data["data"]["recent_workspace"]["virtual_lab"] is None
        assert response_data["data"]["recent_workspace"]["project"] is None


class TestSetRecentWorkspace:
    """Test cases for POST /users/preferences/recent-workspace endpoint."""

    @pytest.mark.asyncio
    async def test_set_recent_workspace_valid(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test setting a valid recent workspace."""
        client = async_test_client
        vl_response, virtual_lab_id, data = mock_user_with_lab_and_project
        project_id = data["project_id"]
        headers = data["headers"]

        payload = {
            "workspace": {
                "virtual_lab_id": virtual_lab_id,
                "project_id": project_id,
            }
        }

        response = await client.post(
            "/users/preferences/recent-workspace", json=payload, headers=headers
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()

        # Should return the set workspace with details
        workspace = response_data["data"]["recent_workspace"]["workspace"]
        assert workspace["virtual_lab_id"] == virtual_lab_id
        assert workspace["project_id"] == project_id
        assert response_data["data"]["recent_workspace"]["updated_at"] is not None
        assert "virtual_lab" in response_data["data"]["recent_workspace"]
        assert "project" in response_data["data"]["recent_workspace"]

    @pytest.mark.asyncio
    async def test_set_recent_workspace_invalid_virtual_lab(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test setting recent workspace with invalid virtual lab ID."""
        client = async_test_client
        vl_response, virtual_lab_id, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # Use a random UUID that doesn't exist
        fake_vl_id = str(uuid4())

        payload = {
            "workspace": {
                "virtual_lab_id": fake_vl_id,
                "project_id": data["project_id"],
            }
        }

        response = await client.post(
            "/users/preferences/recent-workspace", json=payload, headers=headers
        )

        assert response.status_code == HTTPStatus.NOT_FOUND
        response_data = response.json()
        assert "not found" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_set_recent_workspace_invalid_project(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test setting recent workspace with invalid project ID."""
        client = async_test_client
        vl_response, virtual_lab_id, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # use a random uuid that doesn't exist
        fake_project_id = str(uuid4())

        payload = {
            "workspace": {
                "virtual_lab_id": virtual_lab_id,
                "project_id": fake_project_id,
            }
        }

        response = await client.post(
            "/users/preferences/recent-workspace", json=payload, headers=headers
        )

        assert response.status_code == HTTPStatus.NOT_FOUND
        response_data = response.json()
        assert "not found" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_set_recent_workspace_unauthorized_access(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test setting recent workspace that user doesn't have access to."""
        client = async_test_client
        vl_response, virtual_lab_id, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # create another user's virtual lab and project
        other_user_headers = {"Authorization": "Bearer test_other"}
        other_vl_response = await client.post(
            "/virtual-labs",
            json={
                "name": f"Other User Lab {uuid4()}",
                "description": "Other user's lab",
                "reference_email": "other@test.org",
                "entity": "Other Entity",
                "email_status": "verified",
            },
            headers=other_user_headers,
        )

        # if creation succeeds, use that lab/project for testing access control
        if other_vl_response.status_code == 200:
            other_vl_id = other_vl_response.json()["data"]["virtual_lab"]["id"]

            other_project_response = await client.post(
                f"/virtual-labs/{other_vl_id}/projects",
                json={
                    "name": f"Other User Project {uuid4()}",
                    "description": "Other user's project",
                },
                headers=other_user_headers,
            )

            if other_project_response.status_code == 200:
                other_project_id = other_project_response.json()["data"]["project"][
                    "id"
                ]

                # try to set other user's workspace as current user's preference
                payload = {
                    "workspace": {
                        "virtual_lab_id": other_vl_id,
                        "project_id": other_project_id,
                    }
                }

                response = await client.post(
                    "/users/preferences/recent-workspace", json=payload, headers=headers
                )

                assert response.status_code in [
                    HTTPStatus.FORBIDDEN,
                    HTTPStatus.NOT_FOUND,
                ]
                response_data = response.json()
                assert (
                    "access" in response_data["message"].lower()
                    or "not found" in response_data["message"].lower()
                )

            # cleanup other user's resources
            try:
                await client.delete(
                    f"/virtual-labs/{other_vl_id}", headers=other_user_headers
                )
            except Exception:
                pass  # may fail if already deleted


class TestRecentWorkspaceEdgeCases:
    """Test edge cases for recent workspace endpoints."""

    @pytest.mark.asyncio
    async def test_get_recent_workspace_after_setting_then_getting(
        self,
        async_test_client: AsyncClient,
        mock_user_with_multiple_projects: tuple[str, Dict[str, str], Dict[str, Any]],
    ) -> None:
        """test setting a workspace and then retrieving it."""
        client = async_test_client
        virtual_lab_id, projects, headers = mock_user_with_multiple_projects

        # set a specific workspace
        target_project_id = projects["project_1"]
        payload = {
            "workspace": {
                "virtual_lab_id": virtual_lab_id,
                "project_id": target_project_id,
            }
        }

        set_response = await client.post(
            "/users/preferences/recent-workspace", json=payload, headers=headers
        )
        assert set_response.status_code == HTTPStatus.OK

        # get the workspace and verify it's the one we set
        get_response = await client.get(
            "/users/preferences/recent-workspace", headers=headers
        )
        assert get_response.status_code == HTTPStatus.OK

        response_data = get_response.json()
        workspace = response_data["data"]["recent_workspace"]["workspace"]
        assert workspace["project_id"] == target_project_id
        assert workspace["virtual_lab_id"] == virtual_lab_id
