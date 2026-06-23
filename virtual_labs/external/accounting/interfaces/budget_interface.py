from http import HTTPStatus

from httpx import AsyncClient, Response
from httpx._exceptions import HTTPStatusError
from loguru import logger
from pydantic import UUID4

from virtual_labs.core.exceptions.accounting_error import (
    AccountingError,
    AccountingErrorValue,
)
from virtual_labs.external.accounting.models import (
    BudgetAssignResponse,
    BudgetDepleteProjectResponse,
    BudgetDepleteVlabResponse,
    BudgetGrantResponse,
    BudgetMoveResponse,
    BudgetReverseResponse,
    BudgetTopUpResponse,
)
from virtual_labs.infrastructure.settings import settings


def _response_message(response: Response) -> str | None:
    """extraction of an upstream error ``message``.

    the accounting service usually returns a json object with a
    ``message`` key, but error responses can be a list, a scalar, or
    non-json entirely, guard every step so we
    never raise *inside* an exception handler and lose the original error
    """
    try:
        body = response.json()
    except Exception:
        return None
    return body.get("message") if isinstance(body, dict) else None


class BudgetInterface:
    httpx_client: AsyncClient

    def __init__(self, client: AsyncClient, client_token: str):
        self.httpx_client = client
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {client_token}",
        }

    @property
    def _api_url(cls) -> str:
        return f"{settings.ACCOUNTING_BASE_URL}/budget"

    async def top_up(
        self,
        virtual_lab_id: UUID4,
        amount: float,
    ) -> BudgetTopUpResponse:
        """Top-up a virtual lab account."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/top-up",
                headers=self.headers,
                json={
                    "vlab_id": str(virtual_lab_id),
                    "amount": amount,
                },
            )
            response.raise_for_status()
            return BudgetTopUpResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when topping up virtual lab account. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not top up virtual lab account",
                type=AccountingErrorValue.TOP_UP_VIRTUAL_LAB_ACCOUNT_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not top up virtual lab account. Exception: {error}")
            raise AccountingError(
                message=f"Could not top up virtual lab account. Exception: {error}",
                type=AccountingErrorValue.TOP_UP_VIRTUAL_LAB_ACCOUNT_ERROR,
            )

    async def assign(
        self,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        amount: float,
    ) -> BudgetAssignResponse:
        """Move a budget from vlab_id to proj_id."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/assign",
                headers=self.headers,
                json={
                    "vlab_id": str(virtual_lab_id),
                    "proj_id": str(project_id),
                    "amount": amount,
                },
            )
            response.raise_for_status()
            return BudgetAssignResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when assigning project budget. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not assign project budget",
                type=AccountingErrorValue.ASSIGN_PROJECT_BUDGET_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not assign project budget. Exception: {error}")
            raise AccountingError(
                message=f"Could not assign project budget. Exception: {error}",
                type=AccountingErrorValue.ASSIGN_PROJECT_BUDGET_ERROR,
            )

    async def reverse(
        self,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        amount: float,
    ) -> BudgetReverseResponse:
        """Move a budget from proj_id to vlab_id."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/reverse",
                headers=self.headers,
                json={
                    "vlab_id": str(virtual_lab_id),
                    "proj_id": str(project_id),
                    "amount": amount,
                },
            )
            response.raise_for_status()
            return BudgetReverseResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when reversing project budget. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not reverse project budget",
                type=AccountingErrorValue.REVERSE_PROJECT_BUDGET_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not reverse project budget. Exception: {error}")
            raise AccountingError(
                message=f"Could not reverse project bugdet. Exception: {error}",
                type=AccountingErrorValue.REVERSE_PROJECT_BUDGET_ERROR,
            )

    async def move(
        self,
        virtual_lab_id: UUID4,
        debited_from: UUID4,
        credited_to: UUID4,
        amount: float,
    ) -> BudgetMoveResponse:
        """Move a budget between projects belonging to the same virtual lab."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/move",
                headers=self.headers,
                json={
                    "vlab_id": str(virtual_lab_id),
                    "debited_from": str(debited_from),
                    "credited_to": str(credited_to),
                    "amount": amount,
                },
            )
            response.raise_for_status()
            return BudgetMoveResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when moving project budget. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not move project budget",
                type=AccountingErrorValue.MOVE_PROJECT_BUDGET_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not move project budget. Exception: {error}")
            raise AccountingError(
                message=f"Could not move project budget. Exception: {error}",
                type=AccountingErrorValue.MOVE_PROJECT_BUDGET_ERROR,
            )

    async def grant(
        self,
        project_id: UUID4,
        amount: float,
    ) -> BudgetGrantResponse:
        """Top-up and assign budget to a project in one transaction."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/grant",
                headers=self.headers,
                json={
                    "proj_id": str(project_id),
                    "amount": amount,
                },
            )
            response.raise_for_status()
            return BudgetGrantResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when granting project budget. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not grant project budget",
                type=AccountingErrorValue.FUND_PROJECT_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not grant project budget. Exception: {error}")
            raise AccountingError(
                message=f"Could not grant project budget. Exception: {error}",
                type=AccountingErrorValue.FUND_PROJECT_ERROR,
            )

    async def deplete_project(
        self,
        project_id: UUID4,
    ) -> BudgetDepleteProjectResponse:
        """Deplete all credits from a project."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/deplete/project",
                headers=self.headers,
                json={
                    "proj_id": str(project_id),
                },
            )
            response.raise_for_status()
            return BudgetDepleteProjectResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when depleting project budget. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not deplete project budget",
                type=AccountingErrorValue.DEPLETE_PROJECT_BUDGET_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not deplete project budget. Exception: {error}")
            raise AccountingError(
                message=f"Could not deplete project budget. Exception: {error}",
                type=AccountingErrorValue.DEPLETE_PROJECT_BUDGET_ERROR,
            )

    async def deplete_virtual_lab(
        self,
        virtual_lab_id: UUID4,
    ) -> BudgetDepleteVlabResponse:
        """Deplete all credits from all projects and the virtual lab."""
        try:
            response = await self.httpx_client.post(
                f"{self._api_url}/deplete/virtual-lab",
                headers=self.headers,
                json={
                    "vlab_id": str(virtual_lab_id),
                },
            )
            response.raise_for_status()
            return BudgetDepleteVlabResponse.model_validate(response.json())
        except HTTPStatusError as error:
            upstream = _response_message(error.response)
            logger.error(
                f"HTTP Error when depleting virtual lab budget. Error {error}. "
                f"Accounting message: {upstream}"
            )
            raise AccountingError(
                message=upstream or "Could not deplete virtual lab budget",
                type=AccountingErrorValue.DEPLETE_VLAB_BUDGET_ERROR,
                http_status_code=HTTPStatus(error.response.status_code),
            )
        except Exception as error:
            logger.error(f"Could not deplete virtual lab budget. Exception: {error}")
            raise AccountingError(
                message=f"Could not deplete virtual lab budget. Exception: {error}",
                type=AccountingErrorValue.DEPLETE_VLAB_BUDGET_ERROR,
            )
