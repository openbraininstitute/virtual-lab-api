from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.admin import AdminPaymentsListQuery
from virtual_labs.domain.payment import PaymentDetails, PaymentListResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.routes.admin.deps import PLATFORM_ADMIN_TAG_PREFIX
from virtual_labs.usecases.admin import payments as admin_payments

router = APIRouter(tags=[f"{PLATFORM_ADMIN_TAG_PREFIX} | Payments"])


@router.get(
    "/payments",
    response_model=PaymentListResponse,
    summary="List all payments across the platform",
)
async def list_payments(
    params: Annotated[AdminPaymentsListQuery, Query()],
    session: AsyncSession = Depends(default_session_factory),
) -> PaymentListResponse:
    return await admin_payments.list_payments(session, params, user_id=params.user_id)


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentDetails,
    summary="Get any payment by id",
)
async def get_payment(
    payment_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> PaymentDetails:
    return await admin_payments.get_payment(session, payment_id)
