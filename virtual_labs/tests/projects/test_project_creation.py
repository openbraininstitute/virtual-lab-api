from httpx import Response
from requests import get

from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import GroupQueryRepository


def test_vlm_project_creation(
    mock_create_project: tuple[Response, dict[str, str]],
) -> None:
    (response, headers) = mock_create_project

    assert response.status_code == 200
    project_id = response.json()["data"]["project"]["id"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]
    admin_group_name = f"proj/{virtual_lab_id}/{project_id}/admin"
    member_group_name = f"proj/{virtual_lab_id}/{project_id}/member"

    group_repo = GroupQueryRepository()

    admin_group = group_repo.retrieve_group_by_name(name=admin_group_name)
    member_group = group_repo.retrieve_group_by_name(name=member_group_name)

    # Test Kc group creation
    assert admin_group is not None
    assert member_group is not None

    # Test Nexus project creation
    nexus_project = get(
        f"{settings.NEXUS_DELTA_URI}/projects/{virtual_lab_id}/{str(project_id)}",
        headers=headers,
    )

    assert nexus_project.status_code == 200
