import random
from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.shared.utils.billing import amount_to_float


async def retrieve_virtual_lab_balance(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
) -> Response:
    try:
        vlab = await get_undeleted_virtual_lab(session, virtual_lab_id)

        return VliResponse.new(
            message="Virtual lab balance fetched successfully",
            data={
                "virtual_lab_id": virtual_lab_id,
                "budget": amount_to_float(int(vlab.budget_amount)),
                "total_spent": round(
                    random.uniform(0, amount_to_float(int(vlab.budget_amount))), 2
                ),
            },
        )
    except SQLAlchemyError as ex:
        logger.error(f"Error during retrieving virtual lab :({ex})")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.NOT_FOUND,
            message="Retrieving virtual lab failed",
        )
    except Exception as ex:
        logger.error(f"Error during retrieving virtual lab balance ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving virtual lab balance",
        )
