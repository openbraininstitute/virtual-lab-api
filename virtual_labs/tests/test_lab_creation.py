from typing import cast

from fastapi.testclient import TestClient
from requests import get

from virtual_labs.api import app
from virtual_labs.infrastructure.kc.config import kc_auth
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import GroupQueryRepository

client = TestClient(app, base_url="http://localhost:8000")

# TODO: How to cleanup created assets
# TODO: Should I cleanup the created lab in fixture or in test?


# @pytest.fixture(autouse=True)
# def run_around_tests() -> Generator[Any, Any, Any]:
#     print("__BEFORE__")
#     yield
#     # Code that will run after your test, for example:
#     db = default_session_factory()
#     db.query()
#     print("__AFTER__")


def auth(username: str = "test") -> str:
    token = kc_auth.token(username=username, password="test")
    return cast(str, token["access_token"])


def get_headers(username: str = "test") -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {auth(username)}",
    }


def test_virtual_lab_created() -> None:
    body = {
        "name": "Test Lab 15",
        "description": "Test",
        "reference_email": "user@test.org",
        "budget": 10,
        "plan_id": 1,
    }
    headers = get_headers()
    response = client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    # Test that the virtual lab was created
    assert response.status_code == 200
    lab_id = response.json()["data"]["virtual_lab"]["id"]

    group_repo = GroupQueryRepository()
    group_id = f"vlab/{lab_id}/admin"

    # Test that the keycloak admin group was created
    group = group_repo.retrieve_group_by_name(name=group_id)
    assert group is not None

    nexus_org_request = get(
        f"{settings.NEXUS_DELTA_URI}/orgs/{str(lab_id)}", headers=headers
    )
    # Test that the nexus organization was created
    assert nexus_org_request.status_code == 200

    response = client.delete(f"/virtual-labs/{lab_id}", headers=get_headers())
    assert response.status_code == 200
