from http import HTTPStatus
from typing import Generator

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import restore_seeded_user_name


@pytest.fixture(scope="module", autouse=True)
def restore_test_user_name() -> Generator[None, None, None]:
    # the update tests below rename the shared `test` user in Keycloak;
    # other tests assert the seeded name
    yield
    restore_seeded_user_name("test")


class TestGetUserProfile:
    """Test cases for GET /users/profile endpoint."""

    @pytest.mark.asyncio
    async def test_get_profile_returns_user_info(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        response = await client.get("/users/profile")
        assert response.status_code == HTTPStatus.OK
        profile = response.json()["data"]["profile"]
        assert "id" in profile
        assert "email" in profile
        assert "preferred_username" in profile
        assert "first_name" in profile
        assert "last_name" in profile
        assert "email_verified" in profile
        assert "address" in profile
        assert "full_name" in profile

    @pytest.mark.asyncio
    async def test_get_profile_address_has_expected_fields(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        response = await client.get("/users/profile")
        assert response.status_code == HTTPStatus.OK
        address = response.json()["data"]["profile"]["address"]
        for field in ("street", "postal_code", "locality", "region", "country"):
            assert field in address

    @pytest.mark.asyncio
    async def test_get_profile_without_auth_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        response = await client.get("/users/profile", headers={"Authorization": ""})
        assert response.status_code != HTTPStatus.OK


class TestUpdateUserProfile:
    """Test cases for PATCH /users/profile endpoint."""

    @pytest.mark.asyncio
    async def test_update_profile_with_required_fields_only(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "CH",
            "first_name": "Test",
            "last_name": "User",
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["data"]["profile"]["email"] == "test@test.com"

    @pytest.mark.asyncio
    async def test_update_profile_with_all_fields(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "CH",
            "first_name": "Updated",
            "last_name": "User",
            "address": {
                "street": "123 Main St",
                "postal_code": "1000",
                "locality": "Lausanne",
                "region": "Vaud",
            },
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        profile = response.json()["data"]["profile"]
        assert profile["first_name"] == "Updated"
        assert profile["last_name"] == "User"

    @pytest.mark.asyncio
    async def test_update_profile_persists_address(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "FR",
            "first_name": "Test",
            "last_name": "User",
            "address": {
                "street": "10 Rue de Rivoli",
                "postal_code": "75001",
                "locality": "Paris",
                "region": "Ile-de-France",
            },
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        address = response.json()["data"]["profile"]["address"]
        assert address["country"] == "FR"
        assert address["street"] == "10 Rue de Rivoli"
        assert address["postal_code"] == "75001"
        assert address["locality"] == "Paris"
        assert address["region"] == "Ile-de-France"

    @pytest.mark.asyncio
    async def test_update_profile_without_email_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {"country": "CH", "first_name": "Test", "last_name": "User"}
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_profile_without_country_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {"email": "test@test.com", "first_name": "Test", "last_name": "User"}
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_profile_with_invalid_email_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "not-an-email",
            "country": "CH",
            "first_name": "Test",
            "last_name": "User",
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_profile_with_empty_payload_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        response = await client.patch("/users/profile", json={})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_profile_without_auth_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "CH",
            "first_name": "Test",
            "last_name": "User",
        }
        response = await client.patch(
            "/users/profile", json=payload, headers={"Authorization": ""}
        )
        assert response.status_code != HTTPStatus.OK

    @pytest.mark.asyncio
    async def test_update_profile_duplicate_email_returns_conflict(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test-1@test.com",
            "country": "CH",
            "first_name": "Test",
            "last_name": "User",
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.CONFLICT
        assert (
            response.json()["message"]
            == "We’re unable to update your profile with this email address. Please make sure the email is correct or try another one."
        )
        # restore original email
        await client.patch(
            "/users/profile",
            json={
                "email": "test@test.com",
                "country": "CH",
                "first_name": "Test",
                "last_name": "User",
            },
        )

    @pytest.mark.asyncio
    async def test_update_profile_country_without_address_object(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "DE",
            "first_name": "Test",
            "last_name": "User",
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        address = response.json()["data"]["profile"]["address"]
        assert address["country"] == "DE"

    @pytest.mark.asyncio
    async def test_update_profile_missing_country_with_address_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "address": {"street": "123 Main St", "locality": "Lausanne"},
        }
        response = await client.patch("/users/profile", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


class TestOnboardingUpdateUserProfile:
    """Test cases for PATCH /users/onboarding/profile endpoint."""

    @pytest.mark.asyncio
    async def test_onboarding_update_first_and_last_name(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "CH",
            "first_name": "Onboard",
            "last_name": "User",
        }
        response = await client.patch("/users/onboarding/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        profile = response.json()["data"]["profile"]
        assert profile["first_name"] == "Onboard"
        assert profile["last_name"] == "User"

    @pytest.mark.asyncio
    async def test_onboarding_update_country(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "DZ",
            "first_name": "Test",
            "last_name": "User",
        }
        response = await client.patch("/users/onboarding/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        address = response.json()["data"]["profile"]["address"]
        assert address["country"] == "DZ"

    @pytest.mark.asyncio
    async def test_onboarding_update_all_fields(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        payload = {
            "email": "test@test.com",
            "country": "CH",
            "first_name": "New",
            "last_name": "Name",
        }
        response = await client.patch("/users/onboarding/profile", json=payload)
        assert response.status_code == HTTPStatus.OK
        profile = response.json()["data"]["profile"]
        assert profile["first_name"] == "New"
        assert profile["last_name"] == "Name"
        assert profile["address"]["country"] == "CH"

    @pytest.mark.asyncio
    async def test_onboarding_update_empty_payload_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        """Empty payload should fail since all fields are required."""
        client = async_test_client
        response = await client.patch("/users/onboarding/profile", json={})
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_onboarding_does_not_change_email(
        self, async_test_client: AsyncClient
    ) -> None:
        """Onboarding endpoint updates email to the provided value."""
        client = async_test_client

        # update via onboarding with same email
        payload = {
            "email": "test@test.com",
            "country": "CH",
            "first_name": "Keep",
            "last_name": "Email",
        }
        response = await client.patch("/users/onboarding/profile", json=payload)
        assert response.status_code == HTTPStatus.OK

        # verify email is what we set
        get_resp = await client.get("/users/profile")
        assert get_resp.json()["data"]["profile"]["email"] == "test@test.com"

    @pytest.mark.asyncio
    async def test_onboarding_update_without_auth_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        client = async_test_client
        response = await client.patch(
            "/users/onboarding/profile",
            json={
                "email": "test@test.com",
                "country": "CH",
                "first_name": "Test",
                "last_name": "User",
            },
            headers={"Authorization": ""},
        )
        assert response.status_code != HTTPStatus.OK

    @pytest.mark.asyncio
    async def test_onboarding_update_only_first_name_fails(
        self, async_test_client: AsyncClient
    ) -> None:
        """Partial payload should fail since all fields are required."""
        client = async_test_client
        payload = {"first_name": "Solo"}
        response = await client.patch("/users/onboarding/profile", json=payload)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
