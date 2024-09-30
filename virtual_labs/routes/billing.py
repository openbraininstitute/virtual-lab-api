from textwrap import dedent
from typing import Annotated, Tuple, cast

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_vlab_read, verify_vlab_write
from virtual_labs.core.authorization.verify_vlab_read import AuthorizedVlabReadParams
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.payment_method import (
    PaymentMethodCreationBody,
    PaymentMethodDeletionOut,
    PaymentMethodOut,
    PaymentMethodsOut,
    SetupIntentOut,
    StripePaymentOut,
    VlabBalanceOut,
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
async def retrieve_vl_payment_methods(
    auth: AuthorizedVlabReadParams = Depends(verify_vlab_read),
) -> Response:
    return await billing_cases.retrieve_virtual_lab_payment_methods(
        auth["session"], virtual_lab_id=auth["virtual_lab"].uuid
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
    "/{virtual_lab_id}/billing/setup-intent",
    operation_id="generate_setup_intent",
    summary="generate setup intent for a specific stripe customer (customer == virtual lab)",
    description=dedent(
        """
    This endpoint will only generate the setup intent, to be able to use it correctly in attaching
    the payment method to a specific virtual lab, you have to confirm it.

    To confirm the setup intent without using the frontend app, you can access the stripe api docs
    and use the builtin-CLI to confirm the setup intent id.

    ### Stripe dashboard CLI
    You have to use test mode of the stripe account 
    [Stripe Builtin-CLI](https://docs.stripe.com/api/setup_intents/confirm?shell=true&api=true&resource=setup_intents&action=confirm) 

    ### Local machine Stripe CLI

    ```shell 
    stripe setup_intents confirm {setup_intent_id} --payment-method={payment_method}
    ```
    where:
    ```py
    setup_intent_id = `seti_1Mm2cBLkdIwHu7ixaiKW3ElR` # the generated setupIntent 
    payment_method = `pm_card_visa` 
    # it can be any payment method, available in test cards page
    ```

    [Stripe Test cards](https://docs.stripe.com/testing?testing-method=payment-methods)
    """
    ),
    response_model=VliAppResponse[SetupIntentOut],
)
@verify_vlab_write
async def generate_setup_intent(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response:
    return await billing_cases.generate_setup_intent(
        session,
        virtual_lab_id=virtual_lab_id,
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


@router.get(
    "/{virtual_lab_id}/billing/balance",
    operation_id="retrieve_virtual_lab_balance",
    summary="""
    retrieve current balance (budget, total_spent) for a virtual lab
    """,
    description=dedent(
        """
    **The total spent is dummy value for the moment (waiting for the dedicated service to be ready)**
    """
    ),
    response_model=VliAppResponse[VlabBalanceOut],
)
async def retrieve_virtual_lab_balance(
    auth: AuthorizedVlabReadParams = Depends(verify_vlab_read),
) -> Response:
    return await billing_cases.retrieve_virtual_lab_balance(auth["virtual_lab"])
