from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.project import VirtualLabModel
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.is_user_in_list import is_user_in_list
from virtual_labs.shared.utils.uniq_list import uniq_list


def retrieve_single_project_use_case(
    session: Session, virtual_lab_id: UUID4, project_id: UUID4, user_id: UUID4
) -> Response | VliError:
    pr = ProjectQueryRepository(session)
    gqr = GroupQueryRepository()

    try:
        project_vl_tuple = pr.retrieve_one_project_strict(virtual_lab_id, project_id)
        _project = {
            **project_vl_tuple[0].__dict__,
            "virtual_lab": VirtualLabModel(**project_vl_tuple[1].__dict__),
        }
        # TODO: make the two task as async
        admin_list = gqr.retrieve_group_users(group_id=_project["admin_group_id"])
        member_list = gqr.retrieve_group_users(group_id=_project["member_group_id"])
        group_ids = uniq_list([g.id for g in admin_list + member_list])
        is_user_in_list(list_=group_ids, user_id=str(user_id))

    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="No project found",
        )
    except MultipleResultsFound:
        raise VliError(
            error_code=VliErrorCode.MULTIPLE_ENTITIES_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Multiple projects found",
        )
    except SQLAlchemyError:
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Retrieving project failed",
        )
    except UserNotInList:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=status.NOT_ACCEPTABLE,
            message="Fetch project not allowed",
        )
    except Exception as ex:
        logger.error(
            f"Error during retrieve project: {virtual_lab_id}/{project_id} ({ex})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving project",
        )
    else:
        return VliResponse.new(
            message="Project found successfully",
            data={"project": _project},
        )
