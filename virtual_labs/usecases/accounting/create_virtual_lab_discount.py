from decimal import Decimal

from pydantic import UUID4, AwareDatetime

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import CreateDiscountResponse


async def create_virtual_lab_discount(
    virtual_lab_id: UUID4,
    discount: Decimal,
    valid_from: AwareDatetime,
    valid_to: AwareDatetime | None = None,
) -> CreateDiscountResponse:
    return await accounting_service.create_virtual_lab_discount(
        virtual_lab_id=virtual_lab_id,
        discount=discount,
        valid_from=valid_from,
        valid_to=valid_to,
    )
