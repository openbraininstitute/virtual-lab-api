from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.domain.common import PagedResponse, PageParams
from virtual_labs.domain.labs import VirtualLabWithProject
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.usecases.labs.lab_with_not_deleted_projects import (
    lab_with_not_deleted_projects,
)


def paginated_labs_for_user(
    db: Session, page_params: PageParams, user_id: UUID4
) -> PagedResponse[VirtualLabWithProject]:
    user_repo = UserQueryRepository()
    group_ids = [group.id for group in user_repo.retrieve_user_groups(user_id)]
    paginated_results = repository.get_paginated_virtual_labs(
        db, page_params, group_ids=group_ids
    )
    labs = [
        VirtualLabWithProject.model_validate(lab_with_not_deleted_projects(lab))
        for lab in paginated_results
    ]
    return PagedResponse(
        total=len(paginated_results),
        page=page_params.page,
        size=page_params.size,
        results=labs,
    )
