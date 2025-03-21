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
    ProjectReportsResponse,
    VirtualLabReportsResponse,
)
from virtual_labs.infrastructure.settings import settings


class ReportInterface:
    httpx_client: AsyncClient

    def __init__(self, client: AsyncClient, client_token: str):
        self.httpx_client = client
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {client_token}",
        }

    @property
    def _api_url(cls) -> str:
        return f"{settings.ACCOUNTING_BASE_URL}/report"

    async def get_virtual_lab_reports(
        self,
        virtual_lab_id: UUID4,
        page: int,
        page_size: int,
    ) -> VirtualLabReportsResponse:
        try:
            response = await self.httpx_client.get(
                f"{self._api_url}/virtual-lab/{virtual_lab_id}",
                headers=self.headers,
                params={
                    "page": page,
                    "page_size": page_size,
                },
            )
            response.raise_for_status()
            return VirtualLabReportsResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when retrieving virtual lab job reports. Error {error}. Accounting Response: {error.response.json()}"
            )
            raise AccountingError(
                message=f"Could not retrieve virtual lab job reports. Accounting Response: {error.response.json()}",
                type=AccountingErrorValue.FETCH_VIRTUAL_LAB_REPORTS_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(
                f"Could not retrieve virtual lab job reports. Exception {error}"
            )
            raise AccountingError(
                message=f"Could not retrieve virtual lab job reports. Exception: {error}",
                type=AccountingErrorValue.FETCH_VIRTUAL_LAB_REPORTS_ERROR,
            )

    async def get_project_reports(
        self,
        project_id: UUID4,
        page: int,
        page_size: int,
    ) -> ProjectReportsResponse:
        try:
            response = await self.httpx_client.get(
                f"{self._api_url}/project/{project_id}",
                headers=self.headers,
                params={
                    "page": page,
                    "page_size": page_size,
                },
            )
            response.raise_for_status()
            return ProjectReportsResponse.model_validate(response.json())
        except HTTPStatusError as error:
            logger.error(
                f"HTTP Error when retrieving project balance. Error {error}. Accounting Response: {error.response.json()}"
            )
            raise AccountingError(
                message=f"Could not retrieve project balance. Accounting Response: {error.response.json()}",
                type=AccountingErrorValue.FETCH_PROJECT_REPORTS_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not retrieve project balance. Exception {error}")
            raise AccountingError(
                message=f"Could not retrieve project balance. Accounting Response: {error}",
                type=AccountingErrorValue.FETCH_PROJECT_REPORTS_ERROR,
            )
