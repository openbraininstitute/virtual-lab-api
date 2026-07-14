from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.admin import (
    AdminCreditRateDetails,
    AdminCreditRateUpdate,
    AdminTierDetails,
    AdminTierUpdate,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
from virtual_labs.routes.admin.deps import PLATFORM_ADMIN_TAG_PREFIX, platform_admin
from virtual_labs.usecases.admin import plans as admin_plans

router = APIRouter(tags=[f"{PLATFORM_ADMIN_TAG_PREFIX} | Plans"])


@router.get(
    "/plans",
    response_model=list[AdminTierDetails],
    summary="List all subscription tiers, including inactive ones",
)
async def list_tiers(
    session: AsyncSession = Depends(default_session_factory),
) -> list[AdminTierDetails]:
    return await admin_plans.list_tiers(session)


@router.patch(
    "/plans/{tier_id}",
    response_model=AdminTierDetails,
    summary="Update a subscription tier",
    dependencies=[Depends(platform_admin)],
)
async def update_tier(
    tier_id: UUID,
    payload: AdminTierUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> AdminTierDetails:
    return await admin_plans.update_tier(session, tier_id, payload, actor=auth[0])


@router.get(
    "/credit-rates",
    response_model=list[AdminCreditRateDetails],
    summary="List all credit package rates, including inactive ones",
)
async def list_credit_rates(
    currency: str | None = None,
    session: AsyncSession = Depends(default_session_factory),
) -> list[AdminCreditRateDetails]:
    return await admin_plans.list_credit_rates(session, currency)


@router.patch(
    "/credit-rates/{rate_id}",
    response_model=AdminCreditRateDetails,
    summary="Update a credit package rate",
    dependencies=[Depends(platform_admin)],
)
async def update_credit_rate(
    rate_id: UUID,
    payload: AdminCreditRateUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> AdminCreditRateDetails:
    return await admin_plans.update_credit_rate(
        session, rate_id, payload, actor=auth[0]
    )
