from http import HTTPStatus

import stripe
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain import labs as domain
from virtual_labs.repositories import labs as repository


async def update_virtual_lab(
    db: AsyncSession, lab_id: UUID4, lab: domain.VirtualLabUpdate, user_id: UUID4
) -> domain.VirtualLabOut:
    try:
        # Only service admins can update compute_cell
        if lab.compute_cell is not None:
            raise VliError(
                message="Updating compute_cell is not allowed. Only service admins can modify this field.",
                error_code=VliErrorCode.FORBIDDEN_OPERATION,
                http_status_code=HTTPStatus.FORBIDDEN,
            )

        # Exclude compute_cell from update payload for regular users
        lab_dict = lab.model_dump(exclude_unset=True, exclude={"compute_cell"})
        lab_update = domain.VirtualLabUpdate(**lab_dict)
        db_lab = await repository.update_virtual_lab(db, lab_id, lab_update)

        return domain.VirtualLabOut(
            virtual_lab=domain.VirtualLabDetails.model_validate(db_lab)
        )
    except IntegrityError as error:
        logger.error(
            "Virtual lab {} update could not be processed because it violates db constraints {}".format(
                lab_id, error
            )
        )
        raise VliError(
            message="Another virtual lab with same name already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
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
            "Virtual lab {} update could not be processed for unknown database error {}".format(
                lab_id, error
            )
        )

        raise VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except stripe.StripeError as ex:
        logger.error(f"Error during updating stripe customer :({ex})")
        raise VliError(
            message="updating stripe customer failed",
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        )
    except VliError as error:
        raise error
    except Exception as error:
        logger.error(
            "Virtual lab could not be saved due to an unknown error {}".format(error)
        )

        raise VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
