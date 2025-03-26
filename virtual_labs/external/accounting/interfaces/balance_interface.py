from http import HTTPStatus

from httpx import AsyncClient
from httpx._exceptions import HTTPStatusError
from loguru import logger
from pydantic import UUID4

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.models import (
    ProjBalanceResponse,
    VlabBalanceResponse,
)
from virtual_labs.infrastructure.settings import settings


class BalanceInterface:
    httpx_client: AsyncClient

    def __init__(self, client: AsyncClient, client_token: str):
        self.httpx_client = client
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {client_token}",
        }

    @property
    def _api_url(cls) -> str:
        return f"{settings.ACCOUNTING_BASE_URL}/balance"

    async def get_virtual_lab_balance(
        self,
        virtual_lab_id: UUID4,
        include_projects: bool = False,
    ) -> VlabBalanceResponse:
        try:
            response = await self.httpx_client.get(
                f"{self._api_url}/virtual-lab/{virtual_lab_id}",
                headers=self.headers,
                params={"include_projects": include_projects},
            )
            response.raise_for_status()
            return VlabBalanceResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when retrieving virtual lab balance. Error {error}. Accounting Response: {error.response.json()}"
            )
            raise AccountingError(
                message=f"Could not retrieve virtual lab balance. Accounting Response: {error.response.json()}",
                type=AccountingErrorValue.FETCH_VIRTUAL_LAB_BALANCE_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not retrieve virtual lab balance. Exception {error}")
            raise AccountingError(
                message=f"Could not retrieve virtual lab balance. Exception: {error}",
                type=AccountingErrorValue.FETCH_VIRTUAL_LAB_BALANCE_ERROR,
            )

    async def get_project_balance(
        self,
        project_id: UUID4,
    ) -> ProjBalanceResponse:
        try:
            response = await self.httpx_client.get(
                f"{self._api_url}/project/{project_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return ProjBalanceResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when retrieving project balance. Error {error}. Accounting Response: {error.response.json()}"
            )
            raise AccountingError(
                message=f"Could not retrieve project balance. Accounting Response: {error.response.json()}",
                type=AccountingErrorValue.FETCH_PROJECT_BALANCE_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not retrieve project balance. Exception {error}")
            raise AccountingError(
                message=f"Could not retrieve project balance. Accounting Response: {error}",
                type=AccountingErrorValue.FETCH_PROJECT_BALANCE_ERROR,
            )
