from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain import labs as domain
from virtual_labs.repositories import labs as repository


async def update_virtual_lab_compute_cell(
    db: AsyncSession, lab_id: UUID4, compute_cell: domain.ComputeCell
) -> domain.VirtualLabOut:
    """
    Update the compute_cell for a virtual lab.
    This function should only be called by service admins.
    """
    try:
        db_lab = await repository.update_virtual_lab_compute_cell(
            db, lab_id, compute_cell
        )

        return domain.VirtualLabOut(
            virtual_lab=domain.VirtualLabDetails.model_validate(db_lab)
        )
    except NoResultFound:
        raise VliError(
            message="Virtual lab not found",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    except ValueError as error:
        raise VliError(
            message=str(error),
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except SQLAlchemyError as error:
        logger.error(
            "Virtual lab {} compute_cell update could not be processed for database error {}".format(
                lab_id, error
            )
        )

        raise VliError(
            message="Virtual lab compute_cell could not be updated",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except VliError as error:
        raise error
    except Exception as error:
        logger.error(
            "Virtual lab compute_cell could not be updated due to an unknown error {}".format(
                error
            )
        )

        raise VliError(
            message="Virtual lab compute_cell could not be updated",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
