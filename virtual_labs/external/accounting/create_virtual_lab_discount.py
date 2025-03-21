from decimal import Decimal

import httpx
from pydantic import UUID4, AwareDatetime

from virtual_labs.external.accounting.interfaces.discount_interface import (
    DiscountInterface,
)
from virtual_labs.external.accounting.models import CreateDiscountResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def create_virtual_lab_discount(
    virtual_lab_id: UUID4,
    discount: Decimal,
    valid_from: AwareDatetime,
    valid_to: AwareDatetime | None = None,
) -> CreateDiscountResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        discount_interface = DiscountInterface(httpx_client, client_token)
        return await discount_interface.create_discount(
            virtual_lab_id=virtual_lab_id,
            discount=discount,
            valid_from=valid_from,
            valid_to=valid_to,
        )
