from typing import Tuple

from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import (
    verify_project_read,
    verify_vlab_read,
    verify_vlab_write,
)
from virtual_labs.external.accounting.models import (
    BudgetAssignRequest,
    BudgetAssignResponse,
    BudgetReverseRequest,
    BudgetReverseResponse,
    BudgetTopUpRequest,
    BudgetTopUpResponse,
    ProjBalanceResponse,
    ProjectReportsResponse,
    VirtualLabReportsResponse,
    VlabBalanceResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import accounting as accounting_cases

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
    virtual_lab_id: UUID4,
    include_projects: bool = False,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VlabBalanceResponse:
    return await accounting_cases.get_virtual_lab_balance(
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
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> ProjBalanceResponse:
    return await accounting_cases.get_project_balance(project_id)


# Reports endpoints


@router.get(
    "/{virtual_lab_id}/accounting/reports",
    operation_id="retrieve_vl_accounting_job_reports",
    summary="Retrieve accounting job reports for a specific virtual lab",
    response_model=VirtualLabReportsResponse,
)
@verify_vlab_read
async def get_vl_accounting_reports(
    virtual_lab_id: UUID4,
    page: int,
    page_size: int,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VirtualLabReportsResponse:
    return await accounting_cases.get_virtual_lab_reports(
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
    project_id: UUID4,
    page: int,
    page_size: int,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> ProjectReportsResponse:
    return await accounting_cases.get_project_reports(project_id, page, page_size)


# Budget endpoints


# ! This endpoint is only for demo purposes
# TODO: Replace with a proper integration with the payment provider
@router.post(
    "/{virtual_lab_id}/accounting/budget/top-up",
    operation_id="top_up_virtual_lab_account",
    summary="Top-up budget of a specific virtual lab",
    response_model=BudgetTopUpResponse,
)
@verify_vlab_write
async def top_up_virtual_lab_budget(
    virtual_lab_id: UUID4,
    budget_top_up_request: BudgetTopUpRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> BudgetTopUpResponse:
    return await accounting_cases.top_up_virtual_lab_budget(
        virtual_lab_id, budget_top_up_request.amount
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/accounting/budget/assign",  # reverse
    operation_id="assign_project_budget",
    summary="Assign additional budget to a project",
    response_model=BudgetAssignResponse,
)
@verify_vlab_write
async def assign_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    budget_assign_request: BudgetAssignRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> BudgetTopUpResponse:
    return await accounting_cases.assign_project_budget(
        virtual_lab_id, project_id, budget_assign_request.amount
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/accounting/budget/reverse",
    operation_id="reverse_project_budget",
    summary="Transfer some budget from a project to the virtual lab",
    response_model=BudgetReverseResponse,
)
@verify_vlab_write
async def reverse_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    budget_reverse_request: BudgetReverseRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> BudgetTopUpResponse:
    return await accounting_cases.reverse_project_budget(
        virtual_lab_id, project_id, budget_reverse_request.amount
    )
