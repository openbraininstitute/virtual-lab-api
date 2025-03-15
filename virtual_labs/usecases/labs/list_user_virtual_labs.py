import asyncio
from http import HTTPStatus
from typing import Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.common import PageParams, PaginatedResultsResponse
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.shared.utils.auth import (
    get_user_id_from_auth,
)
from virtual_labs.shared.utils.uniq_list import uniq_list


async def list_user_virtual_labs(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
    page_params: PageParams,
) -> PaginatedResultsResponse[VirtualLabDetails]:
    gqr = GroupQueryRepository()
    pqr = ProjectQueryRepository(session=session)

    try:
        user_id = get_user_id_from_auth(auth)
        user_repo = UserQueryRepository()
        group_ids = [group.id for group in user_repo.retrieve_user_groups(user_id)]
        paginated_results = await repository.get_paginated_virtual_labs(
            session, page_params, group_ids=group_ids
        )

        labs: list[VirtualLabDetails] = []

        async def process_lab(lab: VirtualLab) -> VirtualLabDetails:
            admin_users_task = gqr.a_retrieve_group_users(str(lab.admin_group_id))
            member_users_task = gqr.a_retrieve_group_users(str(lab.member_group_id))
            projects_count_task = pqr.retrieve_projects_per_lab_count(
                virtual_lab_id=UUID(str(lab.id))
            )

            admin_users, member_users, projects_count = await asyncio.gather(
                admin_users_task, member_users_task, projects_count_task
            )

            users = admin_users + member_users
            members_count = uniq_list([u.id for u in users])
            lab_details = VirtualLabDetails.model_validate(lab)
            lab_details.projects_count = projects_count
            lab_details.members_count = len(members_count)
            return lab_details

        labs = await asyncio.gather(
            *[process_lab(lab) for lab in paginated_results.rows]
        )

        return PaginatedResultsResponse(
            total=paginated_results.count,
            page=page_params.page,
            page_size=len(paginated_results.rows),
            results=labs,
        )
    except Exception as e:
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=f"Error retrieving virtual labs: {e}",
        )
