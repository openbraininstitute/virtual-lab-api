from dataclasses import dataclass
from http import HTTPStatus as status

from fastapi import Depends
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.repositories.labs import get_virtual_lab_soft
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.is_user_in_lab import is_user_admin_of_lab
from virtual_labs.shared.utils.is_user_in_project import is_user_project_admin

from .verify_user_authenticated import verify_user_authenticated


@dataclass
class VerifiedAdminParams:
    user_id: UUID4
    vlab_id: UUID4
    vlab: VirtualLab | None
    project: Project
    session: AsyncSession


async def verify_user_is_admin(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_id: UUID4 = Depends(verify_user_authenticated),
    session: AsyncSession = Depends(default_session_factory),
) -> VerifiedAdminParams:
    """
    Checks if the user a virtual lab admin or project admin
    """

    pqr = ProjectQueryRepository(session)

    try:
        vlab = await get_virtual_lab_soft(
            session,
            lab_id=virtual_lab_id,
        )
        project = await pqr.retrieve_project_by_id(project_id=project_id)

        is_project_admin = await is_user_project_admin(user_id, project)
        is_vlab_admin = vlab and await is_user_admin_of_lab(user_id, vlab)

        if not is_vlab_admin and not is_project_admin:
            raise VliError(
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=status.FORBIDDEN,
                message="The supplied authentication is not authorized for this action",
            )

    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.NOT_FOUND,
            message="No project with this id found",
        )

    except SQLAlchemyError as e:
        logger.exception(f"SQL Error: {e}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="This project or vlab could not be retrieved from the db",
        )

    except IdentityError:
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=status.UNAUTHORIZED,
            message="User is not authorized to perform operation ",
        )

    except Exception as error:
        logger.exception("Unknown error when checking for authorization", error)
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Checking for authorization failed",
        )

    return VerifiedAdminParams(
        user_id,
        virtual_lab_id,
        vlab=vlab if is_vlab_admin else None,
        project=project,
        session=session,
    )
