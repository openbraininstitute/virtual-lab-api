from typing import Annotated, Tuple

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import (
    verify_vlab_read,
    verify_vlab_write,
)
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.payment_method import (
    PaymentMethodCreationBody,
    PaymentMethodDeletionOut,
    PaymentMethodOut,
    PaymentMethodsOut,
    StripePaymentOut,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import billing as billing_cases

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Billing Endpoints"],
)


@router.get(
    "/{virtual_lab_id}/billing/payment-methods",
    operation_id="retrieve_vl_payment_methods",
    summary="Retrieve payment methods for a specific virtual lab",
    response_model=VliAppResponse[PaymentMethodsOut],
)
@verify_vlab_read
async def retrieve_vl_payment_methods(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    return await billing_cases.retrieve_virtual_lab_payment_methods(
        session,
        virtual_lab_id=virtual_lab_id,
    )


@router.post(
    "/{virtual_lab_id}/billing/payment-methods",
    operation_id="add_new_vl_payment_methods",
    summary="Add new payment method to a specific virtual lab",
    response_model=VliAppResponse[PaymentMethodOut],
)
@verify_vlab_write
async def add_new_payment_method_to_vl(
    virtual_lab_id: UUID4,
    payload: PaymentMethodCreationBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    return await billing_cases.attach_payment_method_to_virtual_lab(
        session,
        virtual_lab_id=virtual_lab_id,
        payload=payload,
        auth=auth,
    )


@router.patch(
    "/{virtual_lab_id}/billing/payment-methods/default",
    operation_id="update_default_payment_method",
    summary="""
    Update default payment method 
    """,
    description="""
    This will be used only for stripe invoice and subscription. 
    for paymentIntent you have to pass the payment method Id
    """,
    response_model=VliAppResponse[PaymentMethodOut],
)
@verify_vlab_write
async def update_default_payment_method(
    virtual_lab_id: UUID4,
    payment_method_id: Annotated[UUID4, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    return await billing_cases.update_default_payment_method(
        session,
        virtual_lab_id=virtual_lab_id,
        payment_method_id=payment_method_id,
        auth=auth,
    )


@router.delete(
    "/{virtual_lab_id}/billing/payment-methods/{payment_method_id}",
    operation_id="delete_payment_method",
    summary="Delete payment method",
    response_model=VliAppResponse[PaymentMethodDeletionOut],
)
@verify_vlab_write
async def delete_payment_method(
    virtual_lab_id: UUID4,
    payment_method_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    return await billing_cases.delete_payment_method_from_vl(
        session,
        virtual_lab_id=virtual_lab_id,
        payment_method_id=payment_method_id,
        auth=auth,
    )


@router.post(
    "/{virtual_lab_id}/billing/budget-topup",
    operation_id="init_vl_budget_topup",
    summary="""
    init virtual lab adding new budget amount processing
    """,
    response_model=VliAppResponse[StripePaymentOut],
)
@verify_vlab_write
async def init_vl_budget_topup(
    virtual_lab_id: UUID4,
    payment_method_id: Annotated[UUID4, Body(embed=True)],
    credit: Annotated[float, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    return await billing_cases.init_vl_budget_topup(
        session,
        virtual_lab_id=virtual_lab_id,
        payment_method_id=payment_method_id,
        credit=credit,
        auth=auth,
    )
