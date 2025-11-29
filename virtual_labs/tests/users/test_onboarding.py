from http import HTTPStatus
from typing import Any, Dict

import pytest
from httpx import AsyncClient


class TestGetOnboardingStatus:
    """Test cases for GET /users/preferences/onboarding endpoint."""

    @pytest.mark.asyncio
    async def test_get_onboarding_status_when_none_set(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test getting onboarding status when no preference is set."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        response = await client.get("/users/preferences/onboarding", headers=headers)

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert response_data["data"] is None or response_data["data"] == {}

    @pytest.mark.asyncio
    async def test_get_onboarding_status_after_update(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test getting onboarding status after setting it."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        update_payload = {
            "completed": False,
            "current_step": 2,
            "dismissed": False,
        }

        await client.put(
            "/users/preferences/onboarding/workspace-data",
            json=update_payload,
            headers=headers,
        )

        # Then get the status
        response = await client.get("/users/preferences/onboarding", headers=headers)

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert "workspace-data" in response_data["data"]
        assert response_data["data"]["workspace-data"]["current_step"] == 2
        assert response_data["data"]["workspace-data"]["completed"] is False


class TestUpdateOnboardingStatus:
    """Test cases for PUT /users/preferences/onboarding/{feature} endpoint."""

    @pytest.mark.asyncio
    async def test_update_onboarding_status_new_feature(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test updating onboarding status for a new feature."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        payload = {
            "completed": False,
            "current_step": 1,
            "dismissed": False,
        }

        response = await client.put(
            "/users/preferences/onboarding/workspace-data",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert "workspace-data" in response_data["data"]
        assert response_data["data"]["workspace-data"]["current_step"] == 1
        assert response_data["data"]["workspace-data"]["completed"] is False
        assert response_data["data"]["workspace-data"]["dismissed"] is False

    @pytest.mark.asyncio
    async def test_update_onboarding_status_mark_completed(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test marking onboarding as completed."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        payload = {
            "completed": True,
        }

        response = await client.put(
            "/users/preferences/onboarding/workspace-project",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert "workspace-project" in response_data["data"]
        assert response_data["data"]["workspace-project"]["completed"] is True
        assert response_data["data"]["workspace-project"]["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_onboarding_status_dismiss(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test dismissing onboarding."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        payload = {"dismissed": True}
        response = await client.put(
            "/users/preferences/onboarding/workspace-workflow",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert "workspace-workflow" in response_data["data"]
        assert response_data["data"]["workspace-workflow"]["dismissed"] is True

    @pytest.mark.asyncio
    async def test_update_onboarding_status_partial_update(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test partial update of onboarding status."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        # First update
        initial_payload = {
            "completed": False,
            "current_step": 1,
            "dismissed": False,
        }

        await client.put(
            "/users/preferences/onboarding/workspace-data",
            json=initial_payload,
            headers=headers,
        )

        # partial update - only update current_step
        update_payload = {"current_step": 3}

        response = await client.put(
            "/users/preferences/onboarding/workspace-data",
            json=update_payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert response_data["data"]["workspace-data"]["current_step"] == 3
        assert response_data["data"]["workspace-data"]["completed"] is False
        assert response_data["data"]["workspace-data"]["dismissed"] is False

    @pytest.mark.asyncio
    async def test_update_onboarding_status_multiple_features(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test updating multiple features independently."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        # update first feature
        payload1 = {
            "completed": True,
        }

        response1 = await client.put(
            "/users/preferences/onboarding/workspace-data",
            json=payload1,
            headers=headers,
        )

        assert response1.status_code == HTTPStatus.OK

        # update second feature
        payload2 = {
            "current_step": 2,
            "completed": False,
        }

        response2 = await client.put(
            "/users/preferences/onboarding/workspace-project",
            json=payload2,
            headers=headers,
        )

        assert response2.status_code == HTTPStatus.OK
        response_data = response2.json()

        assert "workspace-data" in response_data["data"]
        assert "workspace-project" in response_data["data"]
        assert response_data["data"]["workspace-data"]["completed"] is True
        assert response_data["data"]["workspace-project"]["current_step"] == 2


class TestResetOnboardingStatus:
    """Test cases for DELETE /users/preferences/onboarding/{feature} endpoint."""

    @pytest.mark.asyncio
    async def test_reset_onboarding_status_existing_feature(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test resetting onboarding status for an existing feature."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        payload = {
            "completed": False,
            "current_step": 3,
            "dismissed": False,
        }

        await client.put(
            "/users/preferences/onboarding/workspace-data",
            json=payload,
            headers=headers,
        )

        response = await client.delete(
            "/users/preferences/onboarding/workspace-data",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert "workspace-data" not in response_data["data"]

    @pytest.mark.asyncio
    async def test_reset_onboarding_status_non_existing_feature(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test resetting onboarding status for a non-existing feature."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete(
            "/users/preferences/onboarding",
            headers=headers,
        )

        response = await client.delete(
            "/users/preferences/onboarding/workspace-data",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert response_data["data"] is None or response_data["data"] == {}

    @pytest.mark.asyncio
    async def test_reset_onboarding_preserves_other_features(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test that resetting one feature preserves others."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        # set multiple features
        await client.put(
            "/users/preferences/onboarding/workspace-data",
            json={"completed": True},
            headers=headers,
        )

        await client.put(
            "/users/preferences/onboarding/workspace-project",
            json={"current_step": 2},
            headers=headers,
        )

        # reset only one feature
        response = await client.delete(
            "/users/preferences/onboarding/workspace-data",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert "workspace-data" not in response_data["data"]
        assert "workspace-project" in response_data["data"]
        assert response_data["data"]["workspace-project"]["current_step"] == 2


class TestResetAllOnboardingStatus:
    """Test cases for DELETE /users/preferences/onboarding endpoint."""

    @pytest.mark.asyncio
    async def test_reset_all_onboarding_status(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test resetting all onboarding statuses."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        # ensure clean state
        await client.delete("/users/preferences/onboarding", headers=headers)

        # set multiple features
        await client.put(
            "/users/preferences/onboarding/workspace-data",
            json={"completed": True},
            headers=headers,
        )

        await client.put(
            "/users/preferences/onboarding/workspace-project",
            json={"current_step": 2},
            headers=headers,
        )

        await client.put(
            "/users/preferences/onboarding/workspace-workflow",
            json={"dismissed": True},
            headers=headers,
        )

        response = await client.delete(
            "/users/preferences/onboarding",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert response_data["data"] is None or response_data["data"] == {}

    @pytest.mark.asyncio
    async def test_reset_all_onboarding_when_none_exist(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test resetting all onboarding statuses when none exist."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        response = await client.delete(
            "/users/preferences/onboarding",
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        assert response_data["data"] is None or response_data["data"] == {}


class TestOnboardingEdgeCases:
    """Test edge cases for onboarding endpoints."""

    @pytest.mark.asyncio
    async def test_onboarding_empty_payload(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test updating onboarding with empty payload."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        await client.delete("/users/preferences/onboarding", headers=headers)

        await client.put(
            "/users/preferences/onboarding/workspace-data",
            json={"completed": False, "current_step": 1},
            headers=headers,
        )

        response = await client.put(
            "/users/preferences/onboarding/workspace-data",
            json={},
            headers=headers,
        )

        assert response.status_code == HTTPStatus.OK
        response_data = response.json()
        # should preserve existing values
        assert response_data["data"]["workspace-data"]["current_step"] == 1
        assert response_data["data"]["workspace-data"]["completed"] is False

    @pytest.mark.asyncio
    async def test_onboarding_invalid_feature(
        self,
        async_test_client: AsyncClient,
        mock_user_with_lab_and_project: tuple[Any, str, Dict[str, Any]],
    ) -> None:
        """Test updating onboarding with invalid feature name."""
        client = async_test_client
        _, _, data = mock_user_with_lab_and_project
        headers = data["headers"]

        payload = {
            "completed": True,
        }

        response = await client.put(
            "/users/preferences/onboarding/invalid-feature",
            json=payload,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
