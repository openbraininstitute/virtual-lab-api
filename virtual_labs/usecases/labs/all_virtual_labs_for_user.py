from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.common import PageParams, PaginatedResultsResponse
from virtual_labs.domain.labs import VirtualLabWithProject
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.usecases.labs.lab_with_not_deleted_projects import (
    lab_with_not_deleted_projects,
)


async def paginated_labs_for_user(
    db: AsyncSession, page_params: PageParams, user_id: UUID4
) -> PaginatedResultsResponse[VirtualLabWithProject]:
    user_repo = UserQueryRepository()
    group_ids = [group.id for group in user_repo.retrieve_user_groups(user_id)]
    paginated_results = await repository.get_paginated_virtual_labs(
        db, page_params, group_ids=group_ids
    )
    labs = [
        VirtualLabWithProject.model_validate(
            lab_with_not_deleted_projects(lab, user_id)
        )
        for lab in paginated_results.rows
    ]
    return PaginatedResultsResponse(
        total=paginated_results.count,
        page=page_params.page,
        page_size=len(paginated_results.rows),
        results=labs,
    )
