from sqlalchemy.orm import Session

from virtual_labs.domain.common import PagedResponse, PageParams
from virtual_labs.domain.labs import VirtualLabWithProject
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from virtual_labs.usecases.labs.lab_with_not_deleted_projects import (
    lab_with_not_deleted_projects,
)


def all_labs_for_user(db: Session) -> list[models.VirtualLab]:
    # db_labs = repository.get_all_virtual_lab_for_user(db)

    return repository.get_all_virtual_lab_for_user(db)


def paginated_labs_for_user(
    db: Session, page_params: PageParams
) -> PagedResponse[VirtualLabWithProject]:
    paginated_results = repository.get_paginated_virtual_labs(db, page_params)
    labs = [
        VirtualLabWithProject.model_validate(lab_with_not_deleted_projects(lab))
        for lab in paginated_results
    ]
    # TODO: Use keycloak to retrieve filter user labs that belong to the current user
    return PagedResponse(
        total=len(paginated_results),
        page=page_params.page,
        size=page_params.size,
        results=labs,
    )
