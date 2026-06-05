from uuid import UUID

from virtual_labs.core.types import UserRoleEnum


def make_virtual_lab_group_name(virtual_lab_id: UUID, role: UserRoleEnum) -> str:
    return "vlab/{}/{}".format(virtual_lab_id, role.value)


def make_project_group_name(
    virtual_lab_id: UUID, project_id: UUID, role: UserRoleEnum
) -> str:
    return "proj/{}/{}/{}".format(virtual_lab_id, project_id, role.value)
