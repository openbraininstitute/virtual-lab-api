from decimal import Decimal
from http import HTTPStatus

from httpx import AsyncClient
from httpx._exceptions import HTTPStatusError
from loguru import logger
from pydantic import UUID4, AwareDatetime

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.models import (
    CreateDiscountResponse,
)
from virtual_labs.infrastructure.settings import settings


class DiscountInterface:
    httpx_client: AsyncClient

    def __init__(self, client: AsyncClient, client_token: str):
        self.httpx_client = client
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {client_token}",
        }

    @property
    def _api_url(cls) -> str:
        return f"{settings.ACCOUNTING_BASE_URL}/discount"

    async def create_discount(
        self,
        virtual_lab_id: UUID4,
        discount: Decimal,
        valid_from: AwareDatetime,
        valid_to: AwareDatetime | None = None,
    ) -> CreateDiscountResponse:
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}",
                headers=self.headers,
                json={
                    "vlab_id": virtual_lab_id,
                    "discount": str(discount),
                    "valid_from": valid_from.isoformat(),
                    "valid_to": valid_to.isoformat() if valid_to else None,
                },
            )
            response.raise_for_status()
            return CreateDiscountResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when creating virtual lab discount. Error {error}. Accounting Response: {error.response.json()}"
            )
            raise AccountingError(
                message=f"Could not create virtual lab discount. Accounting Response: {error.response.json()}",
                type=AccountingErrorValue.CREATE_VIRTUAL_LAB_DISCOUNT_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not create virtual lab discount. Exception: {error}")
            raise AccountingError(
                message=f"Could not create virtual lab discount. Exception: {error}",
                type=AccountingErrorValue.CREATE_VIRTUAL_LAB_DISCOUNT_ERROR,
            )
