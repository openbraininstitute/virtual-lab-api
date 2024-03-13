from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.labs import VirtualLabUsers
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.group_repo import GroupQueryRepository


def get_virtual_lab_users(db: Session, lab_id: UUID4) -> VirtualLabUsers:
    lab = lab_repository.get_virtual_lab(db, lab_id)

    try:
        group_repository = GroupQueryRepository()

        admins = group_repository.retrieve_group_users(str(lab.admin_group_id))
        members = group_repository.retrieve_group_users(str(lab.member_group_id))

        return VirtualLabUsers(users=admins + members)
    except NoResultFound:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except ValueError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Could not retrieve users from keycloak",
        )
    except SQLAlchemyError as error:
        logger.error(
            f"Virtual lab {lab_id} could not be retrieved due to an unknown database error: {error}"
        )

        raise VliError(
            message="Virtual lab could not be retrieved from the database",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except Exception as error:
        logger.error(f"Users could not be retrieved due to an unknown error {error}")

        raise VliError(
            message="Users could not be retrieved due to an unknown error",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
