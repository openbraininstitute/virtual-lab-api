"""Single-project detail with opt-in field expansion

* always: the project's own fields (`Project` columns) plus its
  `virtual_lab_id`,
* when `expand` contains `admin`: the project admin group's user
  IDs (one Keycloak round-trip),
* when `expand` contains `virtual_lab`: the parent vlab as
  `VirtualLabDetails` — joined from the same row, no extra query.

"""

from __future__ import annotations

import asyncio
from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.project import ProjectDetailExpand, ProjectDetailOut
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.models import UserRepresentation


async def get_project_detail_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    expand: list[ProjectDetailExpand] | None,
) -> ProjectDetailOut:
    requested = set(expand or [])

    try:
        project, virtual_lab = (
            await session.execute(
                select(Project, VirtualLab)
                .join(VirtualLab)
                .where(
                    Project.deleted.is_(False),
                    Project.id == project_id,
                    Project.virtual_lab_id == virtual_lab_id,
                )
            )
        ).one()
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="No project found",
        )
    except MultipleResultsFound:
        logger.error(
            f"Data integrity error: multiple projects for vlab {virtual_lab_id} "
            f"project {project_id}"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Multiple projects found",
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Retrieving project failed",
        )

    admin_task: asyncio.Future[list[str]] | None = None
    if ProjectDetailExpand.admins in requested:
        admin_task = asyncio.ensure_future(
            _retrieve_group_user_ids(str(project.admin_group_id))
        )

    try:
        admin_ids = await admin_task if admin_task is not None else None
    except Exception as exc:
        logger.exception(f"Keycloak error fetching project {project_id} admins: {exc}")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Failed to load project admins",
        )

    found_project = ProjectDetailOut.model_validate(project)
    if admin_ids is not None:
        found_project.admins = admin_ids
    if ProjectDetailExpand.virtual_lab in requested and virtual_lab is not None:
        found_project.virtual_lab = VirtualLabDetails.model_validate(virtual_lab)

    return found_project


async def _retrieve_group_user_ids(group_id: str) -> list[str]:
    members = await KeycloakRealm.a_get_group_members(group_id=group_id)
    return [UserRepresentation(**member).id for member in members]
