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
    ProjAccountCreationResponse,
    VlabAccountCreationResponse,
)
from virtual_labs.infrastructure.settings import settings


class NexusAgentInterface:
    httpx_client: AsyncClient

    def __init__(self, client: AsyncClient, client_token: str):
        self.httpx_client = client
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {client_token}",
        }

    @classmethod
    def get_account_url(cls) -> str:
        return f"{settings.ACCOUNTING_BASE_URL}/account"

    async def create_virtual_lab_account(
        self,
        virtual_lab_id: UUID4,
        name: str,
    ) -> VlabAccountCreationResponse:
        try:
            response = await self.httpx_client.post(
                f"{self.get_account_url()}/",
                headers=self.headers,
                json={
                    "name": name,
                    "id": str(virtual_lab_id),
                },
            )
            response.raise_for_status()
            return VlabAccountCreationResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when creating virtual lab account. Error {error}. Accounting Response: {response.json()}"
            )
            raise AccountingError(
                message=f"Could not create virtual lab account with accounting service. Accounting Response: {response.json()}",
                type=AccountingErrorValue.CREATE_VIRTUAL_LAB_ACCOUNT_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(
                f"Could not create virtual lab account with accounting service. Exception {error}"
            )
            raise AccountingError(
                message=f"Could not create virtual lab account with accounting service. Nexus Response: {error}",
                type=AccountingErrorValue.CREATE_VIRTUAL_LAB_ACCOUNT_ERROR,
            )

    async def create_project_account(
        self,
        project_id: UUID4,
        name: str,
    ) -> ProjAccountCreationResponse:
        try:
            response = await self.httpx_client.post(
                f"{self.get_account_url()}/",
                headers=self.headers,
                json={
                    "name": name,
                    "id": str(project_id),
                },
            )
            response.raise_for_status()
            return ProjAccountCreationResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when creating project account. Error {error}. Accounting Response: {response.json()}"
            )
            raise AccountingError(
                message=f"Could not create project account with accounting service. Accounting Response: {response.json()}",
                type=AccountingErrorValue.CREATE_PROJECT_ACCOUNT_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(
                f"Could not create project account with accounting service. Exception {error}"
            )
            raise AccountingError(
                message=f"Could not create project account with accounting service. Accounting Response: {error}",
                type=AccountingErrorValue.CREATE_PROJECT_ACCOUNT_ERROR,
            )
