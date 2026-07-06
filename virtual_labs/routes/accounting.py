from http import HTTPStatus as status
from typing import Tuple

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import (
    verify_project_read,
    verify_service_admin,
    verify_vlab_or_project_read,
    verify_vlab_read,
)
from virtual_labs.core.authorization.verify_vlab_write import (
    authorize_user_for_vlab_write,
)
from virtual_labs.core.exceptions.accounting_error import AccountingError
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
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
from virtual_labs.infrastructure.kc.config import kc_auth
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases import accounting as accounting_cases

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Accounting Endpoints"],
)


async def _authorize_budget_operation(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> None:
    """Authorize budget assign/reverse: vlab admins OR service admins.

    Additionally, if the vlab has a course, only service admins are allowed.
    """
    _, token = auth
    user_id = str(get_user_id_from_auth(auth))

    # Check if the caller is a service admin
    user_info = kc_auth.userinfo(token=token)
    user_groups = user_info.get("groups", [])
    is_service_admin = VLAB_SERVICE_ADMIN_GROUP in user_groups

    if not is_service_admin:
        # Fall back to vlab admin check
        try:
            await authorize_user_for_vlab_write(
                user_id=user_id,
                virtual_lab_id=virtual_lab_id,
                session=session,
            )
        except UserNotInList:
            raise VliError(
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=status.FORBIDDEN,
                message="The supplied authentication is not authorized for this action",
            )

    # Course vlab restriction: only service admins may operate
    vlab = await get_undeleted_virtual_lab(session, lab_id=virtual_lab_id)
    if vlab.course and not is_service_admin:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=status.FORBIDDEN,
            message="Budget operations are not allowed on course virtual labs",
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
@verify_vlab_or_project_read
async def get_proj_account_balance(
    virtual_lab_id: UUID4,
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


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/accounting/budget/assign",  # reverse
    operation_id="assign_project_budget",
    summary="Assign additional budget to a project",
    response_model=BudgetAssignResponse,
)
async def assign_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    budget_assign_request: BudgetAssignRequest,
    _: None = Depends(_authorize_budget_operation),
) -> BudgetAssignResponse:
    try:
        return await accounting_cases.assign_project_budget(
            virtual_lab_id, project_id, budget_assign_request.amount
        )
    except AccountingError as ex:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            message=ex.message or "Could not complete budget assignment",
            http_status_code=ex.http_status_code or status.INTERNAL_SERVER_ERROR,
        )
    except Exception as ex:
        # never use raw exception text to clients, it can leak few things from accounting
        # return a sanitized message.
        logger.exception(f"Unexpected error during budget assignment: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            message="An unexpected error occurred during budget assignment",
            http_status_code=status.INTERNAL_SERVER_ERROR,
        )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/accounting/budget/reverse",
    operation_id="reverse_project_budget",
    summary="Transfer some budget from a project to the virtual lab",
    response_model=BudgetReverseResponse,
)
async def reverse_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    budget_reverse_request: BudgetReverseRequest,
    _: None = Depends(_authorize_budget_operation),
) -> BudgetReverseResponse:
    try:
        return await accounting_cases.reverse_project_budget(
            virtual_lab_id, project_id, budget_reverse_request.amount
        )
    except AccountingError as ex:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            message=ex.message or "Could not complete budget reversal",
            http_status_code=ex.http_status_code or status.INTERNAL_SERVER_ERROR,
        )
    except Exception as ex:
        # never use raw exception text to clients, it can leak few things from accounting
        # return a sanitized message.
        logger.exception(f"Unexpected error during budget reversal: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            message="An unexpected error occurred during budget reversal",
            http_status_code=status.INTERNAL_SERVER_ERROR,
        )


# Top-up endpoint


@router.post(
    "/{virtual_lab_id}/accounting/budget/top-up",
    operation_id="top_up_virtual_lab_budget",
    summary="Top up a virtual lab budget (service admin only)",
    response_model=BudgetTopUpResponse,
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def top_up_virtual_lab_budget(
    virtual_lab_id: UUID4,
    budget_top_up_request: BudgetTopUpRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> BudgetTopUpResponse:
    try:
        return await accounting_cases.top_up_virtual_lab_budget(
            virtual_lab_id, budget_top_up_request.amount
        )
    except AccountingError as ex:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            message=ex.message or "Could not complete budget top-up",
            http_status_code=ex.http_status_code or status.INTERNAL_SERVER_ERROR,
        )
    except Exception as ex:
        logger.exception(f"Unexpected error during budget top-up: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            message="An unexpected error occurred during budget top-up",
            http_status_code=status.INTERNAL_SERVER_ERROR,
        )
