import json
from http import HTTPStatus

import pytest
from httpx import AsyncClient


class TestGetCountries:
    """Test cases for GET /config/countries endpoint."""

    @pytest.mark.asyncio
    async def test_returns_200(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """The countries endpoint should return 200."""
        response = await async_test_client.get("/config/countries")
        assert response.status_code == HTTPStatus.OK

    @pytest.mark.asyncio
    async def test_returns_json_content_type(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Response should have application/json content type."""
        response = await async_test_client.get("/config/countries")
        assert "application/json" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_returns_list_of_countries(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Response body should be a non-empty list."""
        response = await async_test_client.get("/config/countries")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_each_country_has_name_and_code(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Every entry should have 'name' and 'code' keys."""
        response = await async_test_client.get("/config/countries")
        data = response.json()

        for entry in data:
            assert "name" in entry, f"Missing 'name' in {entry}"
            assert "code" in entry, f"Missing 'code' in {entry}"

    @pytest.mark.asyncio
    async def test_country_codes_are_two_letter_uppercase(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Country codes should be ISO 3166-1 alpha-2 (2 uppercase letters)."""
        response = await async_test_client.get("/config/countries")
        data = response.json()

        for entry in data:
            code = entry["code"]
            assert len(code) == 2, f"Code '{code}' is not 2 characters"
            assert code == code.upper(), f"Code '{code}' is not uppercase"
            assert code.isalpha(), f"Code '{code}' is not alphabetic"

    @pytest.mark.asyncio
    async def test_known_countries_present(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Spot-check that well-known countries are in the list."""
        response = await async_test_client.get("/config/countries")
        data = response.json()
        codes = {entry["code"] for entry in data}

        for expected in ("US", "GB", "DE", "JP", "CH"):
            assert expected in codes, f"Expected country code {expected} not found"

    @pytest.mark.asyncio
    async def test_no_duplicate_codes(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """Country codes should be unique."""
        response = await async_test_client.get("/config/countries")
        data = response.json()
        codes = [entry["code"] for entry in data]
        assert len(codes) == len(set(codes)), "Duplicate country codes found"

    @pytest.mark.asyncio
    async def test_matches_static_file(
        self,
        async_test_client: AsyncClient,
    ) -> None:
        """The endpoint response should match the static country.json file."""
        from pathlib import Path

        static_path = Path(__file__).resolve().parent.parent / "static" / "country.json"
        expected = json.loads(static_path.read_text(encoding="utf-8"))

        response = await async_test_client.get("/config/countries")
        actual = response.json()

        assert actual == expected
