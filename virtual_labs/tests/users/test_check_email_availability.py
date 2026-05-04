from http import HTTPStatus

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers

ENDPOINT = "/users/profile/email/_check"


class TestCheckEmailAvailability:
    """Test cases for GET /users/profile/email/_check endpoint."""

    @pytest.mark.asyncio
    async def test_available_email_returns_204(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """An email that nobody owns should return 204."""
        client = async_test_client
        headers = get_headers()

        response = await client.get(
            ENDPOINT,
            params={"email": "completely-unique-unused@example.com"},
            headers=headers,
        )

        assert response.status_code == HTTPStatus.NO_CONTENT

    @pytest.mark.asyncio
    async def test_own_email_returns_204(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """The caller's own current email should be considered available."""
        client = async_test_client
        headers = get_headers()

        # fetch the caller's current email from their profile
        profile_response = await client.get("/users/profile", headers=headers)
        assert profile_response.status_code == HTTPStatus.OK
        own_email = profile_response.json()["data"]["profile"]["email"]

        response = await client.get(
            ENDPOINT,
            params={"email": own_email},
            headers=headers,
        )

        assert response.status_code == HTTPStatus.NO_CONTENT

    @pytest.mark.asyncio
    async def test_taken_email_returns_422(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """An email owned by a different user should return 422."""
        client = async_test_client
        headers_user_test = get_headers("test")
        headers_user_test1 = get_headers("test-1")

        # get test-1's email
        profile_response = await client.get(
            "/users/profile", headers=headers_user_test1
        )
        assert profile_response.status_code == HTTPStatus.OK
        other_user_email = profile_response.json()["data"]["profile"]["email"]

        # check availability from user "test", should be taken
        response = await client.get(
            ENDPOINT,
            params={"email": other_user_email},
            headers=headers_user_test,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        body = response.json()
        assert "not available" in body["message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_email_returns_422(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """A malformed email should be rejected by Pydantic validation."""
        client = async_test_client
        headers = get_headers()

        response = await client.get(
            ENDPOINT,
            params={"email": "not-an-email"},
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_missing_email_param_returns_422(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Omitting the email query param should return a validation error."""
        client = async_test_client
        headers = get_headers()

        response = await client.get(
            ENDPOINT,
            headers=headers,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """A request without a valid token should be rejected."""
        client = async_test_client

        response = await client.get(
            ENDPOINT,
            params={"email": "someone@example.com"},
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code in (
            HTTPStatus.UNAUTHORIZED,
            HTTPStatus.FORBIDDEN,
        )

    @pytest.mark.asyncio
    async def test_response_does_not_leak_user_info(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """The 422 response should not contain any user details."""
        client = async_test_client
        headers_test = get_headers("test")
        headers_test1 = get_headers("test-1")

        # get test-1's email
        profile_response = await client.get("/users/profile", headers=headers_test1)
        other_email = profile_response.json()["data"]["profile"]["email"]

        response = await client.get(
            ENDPOINT,
            params={"email": other_email},
            headers=headers_test,
        )

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        body = response.json()
        # should not contain any user id, username, or the email itself
        body_str = str(body).lower()
        assert "test-1" not in body_str
        assert other_email.lower() not in body.get("message", "").lower()
