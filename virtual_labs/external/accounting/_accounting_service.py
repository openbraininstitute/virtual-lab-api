from fastapi import Depends
from httpx import AsyncClient
from pydantic import UUID4

from virtual_labs.external.accounting.models import (
    BudgetAssignResponse,
    BudgetMoveResponse,
    BudgetReverseResponse,
    BudgetTopUpResponse,
    ProjAccountCreationResponse,
    ProjBalanceResponse,
    ProjectReportsResponse,
    VirtualLabReportsResponse,
    VlabAccountCreationResponse,
    VlabBalanceResponse,
)
from virtual_labs.infrastructure.kc.auth import get_client_token
from virtual_labs.infrastructure.transport.httpx import httpx_factory

from .interfaces.account_interface import AccountInterface
from .interfaces.balance_interface import BalanceInterface
from .interfaces.budget_interface import BudgetInterface
from .interfaces.report_interface import ReportInterface


class AccountingService:
    """
    service for accounting related operations.
    """

    def __init__(
        self,
        client: AsyncClient,
    ):
        client_token = get_client_token()

        self.account_interface = AccountInterface(
            client=client, client_token=client_token
        )
        self.balance_interface = BalanceInterface(
            client=client, client_token=client_token
        )
        self.budget_interface = BudgetInterface(
            client=client, client_token=client_token
        )
        self.report_interface = ReportInterface(
            client=client, client_token=client_token
        )

    async def assign_project_budget(
        self, virtual_lab_id: UUID4, project_id: UUID4, amount: float
    ) -> BudgetAssignResponse:
        return await self.budget_interface.assign(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=amount,
        )

    async def create_project_account(
        self, virtual_lab_id: UUID4, project_id: UUID4, name: str
    ) -> ProjAccountCreationResponse:
        return await self.account_interface.create_project_account(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            name=name,
        )

    async def create_virtual_lab_account(
        self, virtual_lab_id: UUID4, name: str
    ) -> VlabAccountCreationResponse:
        return await self.account_interface.create_virtual_lab_account(
            virtual_lab_id=virtual_lab_id,
            name=name,
        )

    async def get_project_balance(self, project_id: UUID4) -> ProjBalanceResponse:
        return await self.balance_interface.get_project_balance(
            project_id=project_id,
        )

    async def get_project_reports(
        self, project_id: UUID4, page: int, page_size: int
    ) -> ProjectReportsResponse:
        return await self.report_interface.get_project_reports(
            project_id=project_id,
            page=page,
            page_size=page_size,
        )

    async def get_virtual_lab_balance(
        self, virtual_lab_id: UUID4, include_projects: bool = False
    ) -> VlabBalanceResponse:
        return await self.balance_interface.get_virtual_lab_balance(
            virtual_lab_id=virtual_lab_id,
            include_projects=include_projects,
        )

    async def get_virtual_lab_reports(
        self,
        virtual_lab_id: UUID4,
        page: int,
        page_size: int,
    ) -> VirtualLabReportsResponse:
        return await self.report_interface.get_virtual_lab_reports(
            virtual_lab_id=virtual_lab_id,
            page=page,
            page_size=page_size,
        )

    async def move_project_budget(
        self,
        virtual_lab_id: UUID4,
        debited_from: UUID4,
        credited_to: UUID4,
        amount: float,
    ) -> BudgetMoveResponse:
        return await self.budget_interface.move(
            virtual_lab_id=virtual_lab_id,
            debited_from=debited_from,
            credited_to=credited_to,
            amount=amount,
        )

    async def reverse_project_budget(
        self, virtual_lab_id: UUID4, project_id: UUID4, amount: float
    ) -> BudgetReverseResponse:
        return await self.budget_interface.reverse(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=amount,
        )

    async def top_up_virtual_lab_budget(
        self, virtual_lab_id: UUID4, amount: float
    ) -> BudgetTopUpResponse:
        return await self.budget_interface.top_up(
            virtual_lab_id=virtual_lab_id,
            amount=amount,
        )


def get_accounting_service(
    client: AsyncClient = Depends(httpx_factory),
) -> AccountingService:
    """
    dependency for getting the accounting service.
    """

    return AccountingService(client=client)
