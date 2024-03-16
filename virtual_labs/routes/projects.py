import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from httpx import AsyncClient
from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.project import (
    ProjectBudgetOut,
    ProjectCreationBody,
    ProjectDeletionOut,
    ProjectExistenceOut,
    ProjectOut,
    ProjectPerVLCountOut,
    ProjectUpdateBudgetOut,
    ProjectUsersCountOut,
    ProjectUsersOut,
    ProjectVlOut,
    ProjectWithStarredDateOut,
    ProjectWithVLOut,
    StarProjectsOut,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.transport.httpx import httpx_factory
from virtual_labs.usecases import project as project_cases

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Project Endpoints"],
)


@router.get(
    "/{virtual_lab_id}/projects",
    operation_id="get_all_user_projects_per_vl",
    summary="Retrieve all projects per virtual lab for the authenticated user (only allowed projects)",
    response_model=VliAppResponse[ProjectWithVLOut],
)
def retrieve_projects(
    virtual_lab_id: UUID4, session: Session = Depends(default_session_factory)
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = UUID4("33b376c9-b681-4357-8b0e-ee869e580034")
    return project_cases.retrieve_all_user_projects_per_vl_use_case(
        session, virtual_lab_id, user_id
    )


@router.get(
    "/projects",
    operation_id="get_all_user_projects",
    summary="Retrieve all projects for the authenticated user (only allowed projects)",
    response_model=VliAppResponse[ProjectWithVLOut],
)
def retrieve_all_projects(
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = UUID4("33b376c9-b681-4357-8b0e-ee869e580034")
    return project_cases.retrieve_all_user_projects_use_case(session, user_id)


@router.get(
    "/{virtual_lab_id}/projects/_search",
    operation_id="search_projects_per_vl",
    summary="Fulltext search for only allowed projects per virtual lab for the authenticated user",
    response_model=VliAppResponse[ProjectWithVLOut],
)
def search_projects_per_virtual_lab(
    virtual_lab_id: UUID4,
    q: str = Query(max_length=50, description="query string"),
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = UUID4("33b376c9-b681-4357-8b0e-ee869e580034")
    return project_cases.search_projects_per_virtual_lab_by_name_use_case(
        session, virtual_lab_id, user_id=user_id, query_term=q
    )


@router.get(
    "/projects/_search",
    operation_id="search_all_projects",
    summary="Fulltext search for all allowed projects for the authenticated user",
    response_model=VliAppResponse[ProjectWithVLOut],
)
def search_projects(
    q: str = Query(max_length=50, description="query string"),
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = UUID4("33b376c9-b681-4357-8b0e-ee869e580034")
    return project_cases.search_projects_by_name_use_case(
        session, user_id=user_id, query_term=q
    )


@router.get(
    "/{virtual_lab_id}/projects/_check",
    operation_id="check_project_existence_in_app",
    summary="Look for projects with the same name (case insensitive)",
    response_model=VliAppResponse[ProjectExistenceOut],
)
def check_project_existence(
    q: str | None = Query(max_length=50, description="query string"),
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return project_cases.check_project_existence_use_case(session, query_term=q)


@router.get(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="get_project_by_id",
    summary="Retrieve single project detail per virtual lab",
    response_model=VliAppResponse[ProjectVlOut],
)
def retrieve_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    user_id: UUID4 = UUID4("33b376c9-b681-4357-8b0e-ee869e580034")
    return project_cases.retrieve_single_project_use_case(
        session, virtual_lab_id, project_id, user_id=user_id
    )


@router.post(
    "/{virtual_lab_id}/projects",
    operation_id="create_new_project",
    summary="Create a new project for a virtual lab",
    description=(
        """
        Allow only the User that has the right role (based on KC groups 'Admin')  
        to create a new project for a specific virtual lab
        """
    ),
    response_model=VliAppResponse[ProjectOut],
)
async def create_new_project(
    virtual_lab_id: UUID4,
    payload: ProjectCreationBody,
    session: Session = Depends(default_session_factory),
    httpx_clt: AsyncClient = Depends(httpx_factory),
) -> Response | VliError:
    # TODO: get user_id from token
    user_id: UUID4 = uuid.UUID("a188837d-19ac-4ebc-b14f-a90b663357b3")
    return await project_cases.create_new_project_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        user_id=user_id,
        payload=payload,
        httpx_clt=httpx_clt,
    )


@router.delete(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="delete_project",
    summary="Delete project of a virtual lab if the user has permission",
    description=(
        """
        Allow only the User that has the right role (based on KC groups "Admin")
        to delete a project from a specific virtual lab
        The deletion is logic so the data will be preserved in the db and only
        the `deleted`, `deleted_at` properties will be updated
        """
    ),
    response_model=VliAppResponse[ProjectDeletionOut],
)
def delete_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    user_id: UUID4 = UUID4("33b376c9-b681-4357-8b0e-ee869e580034")
    return project_cases.delete_project_use_case(
        session, project_id=project_id, virtual_lab_id=virtual_lab_id, user_id=user_id
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/budget",
    operation_id="get_project_budget",
    summary="Retrieve project budget",
    response_model=VliAppResponse[ProjectBudgetOut],
)
def retrieve_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return project_cases.retrieve_project_budget_use_case(
        session, virtual_lab_id=virtual_lab_id, project_id=project_id
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/budget",
    operation_id="update_project_budget",
    summary="Update project budget if the user has permission",
    description=(
        """
        Allow only the User that has the right role (based on KC groups "Virtual Lab Admin")
        to update the project budget from a specific virtual lab
        A check will be run to verify if the Virtual lab has the requested amount for the new budget
        """
    ),
    response_model=VliAppResponse[ProjectUpdateBudgetOut],
)
def update_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    new_budget: Annotated[float, Body(embed=True)],
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    user_id: UUID4 = uuid.UUID("a188837d-19ac-4ebc-b14f-a90b663357b3")
    return project_cases.update_project_budget_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        user_id=user_id,
        value=new_budget,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/users",
    operation_id="get_project_users",
    summary="Retrieve users per project",
    response_model=VliAppResponse[ProjectUsersOut],
)
def retrieve_project_users(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return project_cases.retrieve_all_users_per_project_use_case(
        session, virtual_lab_id, project_id
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/users/count",
    operation_id="get_project_users_count",
    summary="Retrieve users count per project",
    response_model=VliAppResponse[ProjectUsersCountOut],
)
def retrieve_project_users_count(
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return project_cases.retrieve_users_per_project_count_use_case(session, project_id)


@router.get(
    "/{virtual_lab_id}/projects/count",
    operation_id="get_project_per_vl_count",
    summary="Retrieve virtual lab projects count",
    response_model=VliAppResponse[ProjectPerVLCountOut],
)
def retrieve_projects_per_vl_count(
    virtual_lab_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return project_cases.retrieve_projects_count_per_virtual_lab_use_case(
        session, virtual_lab_id=virtual_lab_id
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/star-status",
    operation_id="star_or_unstar_project",
    summary="Star/Unstar (Pin/Unpin) project",
    tags=["Project Endpoints"],
    description=(
        """
        Allow only the User that has the right role (be part of the project)
        Star or Unstar (Pin/Unpin) a project
        """
    ),
    response_model=VliAppResponse[ProjectWithStarredDateOut],
)
def update_project_star_status(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = uuid.UUID("a188837d-19ac-4ebc-b14f-a90b663357b3")
    return project_cases.update_star_project_status_use_case(
        session, virtual_lab_id=virtual_lab_id, project_id=project_id, user_id=user_id
    )


@router.get(
    "/projects/stars",
    operation_id="get_star_projects",
    summary="Retrieve star projects",
    description=(
        """
        Allow only the User that has the right role (be part of the project)
        Retrieve the star projects for a specific user
        """
    ),
    response_model=VliAppResponse[StarProjectsOut],
)
def retrieve_stars_project(
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = uuid.UUID("a188837d-19ac-4ebc-b14f-a90b663357b3")
    return project_cases.retrieve_starred_projects_use_case(session, user_id=user_id)
