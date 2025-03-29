from typing import Literal

from pydantic import UUID4, BaseModel
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.shared.utils.uniq_list import uniq_list


class MembershipResult(BaseModel):
    has_membership: bool
    is_vlab_owner: bool
    is_project_owner: bool


async def has_group_membership(
    session: AsyncSession,
    user_id: UUID4,
    virtual_lab_id: UUID4,
    project_id: UUID4 | None,
    role: Literal["admin", "member", "both"],
    ctx: Literal["vlab", "project"],
) -> MembershipResult:
    """
    Check if a user has membership in specific groups and extract owned groups.

    Args:
        session: Database session
        user_id: The user ID to check
        virtual_lab_id: The virtual lab ID to check
        project_id: The project ID to check (required when scope is 'project')
        filter: Which role to check for - 'admin', 'member', or 'both'
        ctx: Whether to check virtual lab or project membership

    """
    repo = GroupQueryRepository()
    user_groups = await repo.a_retrieve_user_groups(user_id=str(user_id))
    vlab_result = await session.execute(
        select(VirtualLab)
        .filter(VirtualLab.id == virtual_lab_id, VirtualLab.deleted == false())
        .options(joinedload(VirtualLab.projects))
    )
    virtual_lab = vlab_result.scalars().first()

    owned_admin_group_id = [str(virtual_lab.admin_group_id)] if virtual_lab else []
    owned_project_admin_groups: list[str] = []
    if virtual_lab:
        owned_project_admin_groups = [
            str(project.id)
            for project in list(
                filter(lambda x: x.deleted is False, virtual_lab.projects)
            )
        ]
    all_subscribed_user_group_ids = [group.id for group in user_groups]

    is_vlab_owner = owned_admin_group_id == virtual_lab_id if virtual_lab else False
    is_project_owner = project_id in owned_project_admin_groups if project_id else False

    vlab_admin_group_ids = [
        group_id
        for group_id in all_subscribed_user_group_ids
        if group_id.startswith("vlab/") and group_id.endswith("/admin")
    ]
    vlab_member_group_ids = [
        group_id
        for group_id in all_subscribed_user_group_ids
        if group_id.startswith("proj/") and group_id.endswith("/member")
    ]
    project_admin_group_ids = [
        group_id
        for group_id in all_subscribed_user_group_ids
        if group_id.startswith("proj/") and group_id.endswith("/admin")
    ]
    project_member_group_ids = [
        group_id
        for group_id in all_subscribed_user_group_ids
        if group_id.startswith("vlab/") and group_id.endswith("/member")
    ]

    has_membership = False
    current_vlab_admin_group_id = ""
    current_vlab_member_group_id = ""
    current_project_admin_group_id = ""
    current_project_member_group_id = ""

    if virtual_lab_id:
        current_vlab_admin_group_id = f"vlab/{virtual_lab_id}/admin"
        current_vlab_member_group_id = f"vlab/{virtual_lab_id}/member"
    if project_id:
        current_project_admin_group_id = f"proj/{virtual_lab_id}/{project_id}/admin"
        current_project_member_group_id = f"proj/{virtual_lab_id}/{project_id}/member"

    if ctx == "vlab":
        if role == "admin":
            has_membership = current_vlab_admin_group_id in vlab_admin_group_ids
        elif role == "member":
            has_membership = current_vlab_member_group_id in uniq_list(
                vlab_member_group_ids + owned_admin_group_id
            )
        elif role == "both":
            has_membership = current_vlab_admin_group_id in uniq_list(
                vlab_admin_group_ids + owned_admin_group_id + vlab_member_group_ids
            )

    elif ctx == "project" and project_id:
        if role == "admin":
            has_membership = current_project_admin_group_id in uniq_list(
                project_admin_group_ids + owned_project_admin_groups
            )
        elif role == "member":
            has_membership = current_project_member_group_id in uniq_list(
                project_member_group_ids + owned_project_admin_groups
            )
        elif role == "both":
            has_membership = current_project_admin_group_id in uniq_list(
                project_admin_group_ids
                + project_member_group_ids
                + owned_project_admin_groups
                + owned_project_admin_groups
            )

    return MembershipResult(
        has_membership=has_membership,
        is_vlab_owner=is_vlab_owner,
        is_project_owner=is_project_owner,
    )
