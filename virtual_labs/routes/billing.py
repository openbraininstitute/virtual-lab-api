from http import HTTPStatus
from typing import Tuple

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.billing import (
    BillingQuoteResponse,
    CreateBillingQuoteRequest,
    CreditConversionRequest,
    CreditConversionResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.credit_exchange_rate_repo import (
    CreditExchangeRateQueryRepository,
)
from virtual_labs.services.billing import BillingQuoteService, quote_to_response
from virtual_labs.services.credit_converter import CreditConverter
from virtual_labs.shared.utils.auth import get_user_id_from_auth

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.post(
    "/quotes",
    operation_id="create_billing_quote",
    summary="Create a tax-aware billing quote",
    response_model=VliAppResponse[BillingQuoteResponse],
)
async def create_billing_quote(
    payload: CreateBillingQuoteRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    try:
        quote = await BillingQuoteService(session).create_quote(
            payload=payload,
            user_id=get_user_id_from_auth(auth),
        )
    except ValueError as exc:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=str(exc),
        ) from exc
    return VliResponse.new(
        message="Billing quote created successfully",
        data=quote_to_response(quote).model_dump(),
    )


@router.post(
    "/credit-conversions",
    operation_id="convert_billing_credits",
    summary="Convert credits to a currency subtotal",
    response_model=VliAppResponse[CreditConversionResponse],
)
async def convert_billing_credits(
    payload: CreditConversionRequest,
    session: AsyncSession = Depends(default_session_factory),
    _auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    try:
        converter = CreditConverter(
            exchange_rate_repo=CreditExchangeRateQueryRepository(session=session)
        )
        amount = await converter.credits_to_currency(
            payload.credits,
            payload.currency,
        )
        rate = await converter.get_exchange_rate(payload.currency)
    except ValueError as exc:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=str(exc),
        ) from exc

    return VliResponse.new(
        message="Credits converted successfully",
        data=CreditConversionResponse(
            credits=payload.credits,
            currency=payload.currency,
            amount=int(amount),
            rate=rate,
        ).model_dump(),
    )
