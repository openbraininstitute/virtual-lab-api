from fastapi import APIRouter
from pydantic import UUID4

from virtual_labs.core.authorization import verify_project_read, verify_vlab_read
from virtual_labs.external.accounting import balance as accounting_balance
from virtual_labs.external.accounting import report as accounting_report
from virtual_labs.external.accounting.models import (
    ProjBalanceResponse,
    ProjectReportsResponse,
    VirtualLabReportsResponse,
    VlabBalanceResponse,
)

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Accounting Endpoints"],
)


# Balance endpoints


@router.get(
    "/{virtual_lab_id}/accounting/balance",
    operation_id="retrieve_vl_account_balance",
    summary="Retrieve account balance for a specific virtual lab",
    response_model=VlabBalanceResponse,
)
@verify_vlab_read
async def get_vl_account_balance(
    virtual_lab_id: UUID4, include_projects: bool = False
) -> VlabBalanceResponse:
    return await accounting_balance.get_virtual_lab_balance(
        virtual_lab_id, include_projects
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/accounting/balance",
    operation_id="retrieve_proj_account_balance",
    summary="Retrieve account balance for a specific project",
    response_model=ProjBalanceResponse,
)
@verify_project_read
async def get_proj_account_balance(
    project_id: UUID4,
) -> ProjBalanceResponse:
    return await accounting_balance.get_project_balance(project_id)


# Reports endpoints


@router.get(
    "/{virtual_lab_id}/accounting/reports",
    operation_id="retrieve_vl_accounting_job_reports",
    summary="Retrieve accounting job reports for a specific virtual lab",
    response_model=VirtualLabReportsResponse,
)
@verify_vlab_read
async def get_vl_accounting_reports(
    virtual_lab_id: UUID4, page: int, page_size: int
) -> VirtualLabReportsResponse:
    return await accounting_report.get_virtual_lab_reports(
        virtual_lab_id, page, page_size
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/accounting/reports",
    operation_id="retrieve_proj_accounting_job_reports",
    summary="Retrieve accounting job reports for a specific project",
    response_model=ProjectReportsResponse,
)
@verify_project_read
async def get_proj_accounting_reports(
    project_id: UUID4, page: int, page_size: int
) -> ProjectReportsResponse:
    return await accounting_report.get_project_reports(project_id, page, page_size)
