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
from typing import Literal

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.project import ProjectDetailOut
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository

ExpandField = Literal["admin", "virtual_lab"]
_VALID_EXPANDS: frozenset[ExpandField] = frozenset(("admin", "virtual_lab"))


def _normalize_expand(expand: list[str] | None) -> set[ExpandField]:
    """Validate and deduplicate expand keys.

    Unknown values raise `VliError(INVALID_REQUEST)` so clients get a
    clear error rather than a silently-ignored typo.
    """
    if not expand:
        return set()
    valid: set[ExpandField] = set()
    unknown: list[str] = []
    for raw in expand:
        if raw in _VALID_EXPANDS:
            # Manual narrowing: mypy doesn't propagate the membership
            # check on a frozenset into the Literal type.
            valid.add(raw)  # type: ignore[arg-type]
        else:
            unknown.append(raw)
    if unknown:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Unknown expand value",
            details=f"Unknown: {unknown}; allowed: {sorted(_VALID_EXPANDS)}",
        )
    return valid


async def get_project_detail_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    expand: list[str] | None,
    auth: tuple[AuthUserGrants, str],
) -> Response:
    requested = _normalize_expand(expand)

    project_repo = ProjectQueryRepository(session)

    try:
        project, virtual_lab = await project_repo.retrieve_one_project_strict(
            virtual_lab_id, project_id
        )
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="No project found",
        )
    except MultipleResultsFound:
        raise VliError(
            error_code=VliErrorCode.MULTIPLE_ENTITIES_FOUND,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Multiple projects found",
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Retrieving project failed",
        )

    admin_task: asyncio.Future[list[str]] | None = None
    if "admin" in requested:
        admin_task = asyncio.ensure_future(
            GroupQueryRepository().a_retrieve_group_user_ids(
                group_id=str(project.admin_group_id)
            )
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

    detail = ProjectDetailOut.model_validate(project)
    if admin_ids is not None:
        detail.admin = admin_ids
    if "virtual_lab" in requested and virtual_lab is not None:
        detail.virtual_lab = VirtualLabDetails.model_validate(virtual_lab)

    return VliResponse.new(
        message="Project found successfully",
        data=detail.model_dump(exclude_none=True),
    )
