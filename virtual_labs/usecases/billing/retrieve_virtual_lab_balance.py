import random
from http import HTTPStatus as status

from fastapi.responses import Response
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.shared.utils.billing import amount_to_float


async def retrieve_virtual_lab_balance(
    vlab: VirtualLab,
) -> Response:
    try:
        return VliResponse.new(
            message="Virtual lab balance fetched successfully",
            data={
                "virtual_lab_id": vlab.uuid,
                "budget": amount_to_float(int(vlab.budget_amount)),
                "total_spent": round(
                    random.uniform(0, amount_to_float(int(vlab.budget_amount))), 2
                ),
            },
        )
    except Exception as ex:
        logger.error(f"Error during retrieving virtual lab balance ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during retrieving virtual lab balance",
        )
