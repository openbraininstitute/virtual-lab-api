from http import HTTPStatus
from typing import Tuple

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization.verify_vlab_write import (
    authorize_user_for_vlab_write,
)
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.billing import (
    BillingQuoteResponse,
    CreateBillingQuoteRequest,
    CreditConversionRequest,
    CreditConversionResponse,
    CreditPackageRateItem,
    CreditPackageRatesResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.credit_package_rate_repo import (
    CreditPackageRateRepository,
)
from virtual_labs.services.billing import BillingQuoteService, quote_to_response
from virtual_labs.services.credit_converter import CreditConverter
from virtual_labs.shared.utils.auth import get_user_id_from_auth

router = APIRouter(prefix="/billing", tags=["Billing"])


async def authorize_quote_virtual_lab_write(
    *,
    payload: CreateBillingQuoteRequest,
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> None:
    forbidden = VliError(
        error_code=VliErrorCode.NOT_ALLOWED_OP,
        http_status_code=HTTPStatus.FORBIDDEN,
        message="The supplied authentication is not authorized for this action",
    )
    try:
        is_authorized = await authorize_user_for_vlab_write(
            user_id=str(get_user_id_from_auth(auth)),
            virtual_lab_id=payload.virtual_lab_id,
            session=session,
        )
    except VliError:
        raise
    except Exception:
        raise forbidden
    if not is_authorized:
        raise forbidden


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
    await authorize_quote_virtual_lab_write(
        payload=payload,
        session=session,
        auth=auth,
    )
    try:
        quote = await BillingQuoteService(session).create_quote(
            payload=payload,
            user_id=get_user_id_from_auth(auth),
        )
    except VliError:
        raise
    except Exception as exc:
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
    summary="Convert credits to a currency subtotal with volume pricing",
    response_model=VliAppResponse[CreditConversionResponse],
)
async def convert_billing_credits(
    payload: CreditConversionRequest,
    session: AsyncSession = Depends(default_session_factory),
    _auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    try:
        converter = CreditConverter(
            package_rate_repo=CreditPackageRateRepository(session=session)
        )
        result = await converter.convert_credits(
            payload.credits,
            payload.currency,
        )
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
            amount=result.amount,
            rate=result.rate,
            discount_pct=result.discount_pct,
            base_rate=result.base_rate,
        ).model_dump(),
    )


@router.get(
    "/credit-package-rates",
    operation_id="list_credit_package_rates",
    summary="List all active credit package rates for a currency",
    response_model=VliAppResponse[CreditPackageRatesResponse],
)
async def list_credit_package_rates(
    currency: str = Query(default="chf", min_length=3, max_length=3),
    session: AsyncSession = Depends(default_session_factory),
    _auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    repo = CreditPackageRateRepository(session=session)
    tiers = await repo.get_all_active_rates(currency.lower())

    if not tiers:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=f"No pricing rates configured for currency: {currency}",
        )

    return VliResponse.new(
        message="Credit package rates retrieved",
        data=CreditPackageRatesResponse(
            currency=currency.lower(),
            rates=[
                CreditPackageRateItem(
                    min_credits=tier.min_credits,
                    max_credits=tier.max_credits,
                    rate=tier.rate,
                    discount_pct=tier.discount_pct,
                )
                for tier in tiers
            ],
        ).model_dump(),
    )
