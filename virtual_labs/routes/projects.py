import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from httpx import AsyncClient
from pydantic import UUID4, EmailStr
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.project import (
    ProjectBudgetOut,
    ProjectCreationModel,
    ProjectDeletionOut,
    ProjectExistenceOut,
    ProjectOut,
    ProjectsOut,
    ProjectUpdateBudgetOut,
    ProjectWithStarredDateOut,
    StarProjectsOut,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.transport.httpx import httpx_factory
from virtual_labs.usecases import project as cases

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Project Endpoints"],
)


@router.get(
    "/{virtual_lab_id}/projects",
    operation_id="get_projects",
    summary="Retrieve projects per virtual lab for a specific user (only allowed projects)",
    response_model=VliAppResponse[ProjectsOut],
)
def retrieve_projects(
    virtual_lab_id: UUID4, session: Session = Depends(default_session_factory)
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = uuid.uuid4()
    return cases.retrieve_user_projects_use_case(session, virtual_lab_id, user_id)


@router.get(
    "/{virtual_lab_id}/projects/_search",
    operation_id="search_projects",
    summary="Fulltext search for only allowed projects per virtual lab for a specific user",
    response_model=VliAppResponse[ProjectsOut],
)
def search_projects_per_virtual_lab(
    virtual_lab_id: UUID4,
    q: str | None = Query(max_length=50, description="query string"),
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO get it from token
    user_id: UUID4 = uuid.uuid4()
    return cases.search_projects_per_virtual_lab_by_name_use_case(
        session, virtual_lab_id, user_id=user_id, query_term=q
    )


@router.get(
    "/{virtual_lab_id}/projects/_check",
    operation_id="check_project_existence_in_app",
    summary="Look for projects with the same name case insensitive",
    response_model=VliAppResponse[ProjectExistenceOut],
)
def check_project_existence(
    q: str | None = Query(max_length=50, description="query string"),
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return cases.check_project_existence_use_case(session, query_term=q)


@router.get(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="get_project_by_id",
    summary="Retrieve single project detail per virtual lab",
    response_model=VliAppResponse[ProjectOut],
)
def retrieve_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    return cases.retrieve_single_project_use_case(session, virtual_lab_id, project_id)


@router.post(
    "/{virtual_lab_id}/projects",
    operation_id="create_new_project",
    summary="Create a new project for a virtual lab",
    response_model=VliAppResponse[ProjectOut],
)
async def create_new_project(
    virtual_lab_id: UUID4,
    payload: ProjectCreationModel,
    session: Session = Depends(default_session_factory),
    httpx_clt: AsyncClient = Depends(httpx_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (based on KC groups "Admin")
    to create a new project for a specific virtual lab
    """
    return await cases.create_new_project_use_case(
        session, virtual_lab_id=virtual_lab_id, payload=payload, httpx_clt=httpx_clt
    )


@router.delete(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="delete_project",
    summary="Delete project of a virtual lab if the user has permission",
    response_model=VliAppResponse[ProjectDeletionOut],
)
def delete_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (based on KC groups "Admin")
    to delete a project from a specific virtual lab
    The deletion is logic so the data will be preserved in the db and only
    the `deleted`, `deleted_at` properties will be updated
    """
    return cases.delete_project_use_case(
        session, project_id=project_id, virtual_lab_id=virtual_lab_id
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
    return cases.retrieve_project_budget_use_case(
        session, virtual_lab_id=virtual_lab_id, project_id=project_id
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/budget",
    operation_id="update_project_budget",
    summary="Update project budget if the user has permission",
    response_model=VliAppResponse[ProjectUpdateBudgetOut],
)
def update_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    new_budget: Annotated[float, Body(embed=True)],
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (based on KC groups "Virtual Lab Admin")
    to update the project budget from a specific virtual lab
    A check will be run to verify if the Virtual lab has the requested amount for the new budget
    """
    return cases.update_project_budget_use_case(
        session, virtual_lab_id=virtual_lab_id, project_id=project_id, value=new_budget
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/users",
    operation_id="get_project_users",
    summary="Retrieve users per project",
    tags=["Not Yet Implemented"],
    response_model=VliAppResponse[None],
)
def retrieve_project_users(
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO: need more work
    return cases.retrieve_all_users_per_project_use_case(session, project_id)


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/users/count",
    operation_id="get_project_users_count",
    summary="Retrieve users count per project",
    tags=["Not Yet Implemented"],
    response_model=VliAppResponse[None],
)
def retrieve_project_users_count(
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    # TODO: need more work
    return cases.retrieve_users_per_project_count_use_case(session, project_id)


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/attach",
    operation_id="attach_user_to_project",
    summary="Attach user to project",
    tags=["Not Yet Implemented"],
    response_model=VliAppResponse[None],
)
def attach_user_to_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_email: Annotated[EmailStr, Body(embed=True)],
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (based on KC groups "Virtual Lab Admin/Project Admin")
    Attach a user to a project
    """
    # TODO: need more work
    return cases.attach_user_to_project_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        user_email=user_email,
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/detach",
    operation_id="detach_user_to_project",
    summary="Detach user to project",
    tags=["Not Yet Implemented"],
    response_model=VliAppResponse[None],
)
def detach_user_to_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_email: Annotated[EmailStr, Body(embed=True)],
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (based on KC groups "Virtual Lab Admin/Project Admin")
    Detach a user from a project
    """
    # TODO: need more work
    return cases.detach_user_from_project_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        user_email=user_email,
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/star-status",
    operation_id="star_or_unstar_project",
    summary="Star/Unstar (Pin/Unpin) project",
    tags=["Project Endpoints"],
    response_model=VliAppResponse[ProjectWithStarredDateOut],
)
def update_project_star_status(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (be part of the project)
    Star or Unstar (Pin/Unpin) a project
    """
    # TODO get it from token
    user_id: UUID4 = uuid.UUID("70d1de79-d4d1-4eba-a4c5-da016316b951", version=4)
    return cases.update_star_project_status_use_case(
        session, virtual_lab_id=virtual_lab_id, project_id=project_id, user_id=user_id
    )


@router.get(
    "/projects/stars",
    operation_id="get_star_projects",
    summary="Retrieve star projects",
    response_model=VliAppResponse[StarProjectsOut],
)
def retrieve_stars_project(
    session: Session = Depends(default_session_factory),
) -> Response | VliError:
    """
    Allow only the User that has the right role (be part of the project)
    Retrieve the star projects for a specific user
    """
    # TODO get it from token
    user_id: UUID4 = uuid.UUID("70d1de79-d4d1-4eba-a4c5-da016316b951", version=4)
    return cases.retrieve_starred_projects_use_case(session, user_id=user_id)
