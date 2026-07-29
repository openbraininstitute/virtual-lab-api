"""Platform-admin operations over subscription tiers and credit
package rates. Stripe-side fields (product/price ids, amounts) stay
read-only here — they are managed by the Stripe-driven seeding
scripts (`populate-tiers`, `seed_credit_package_rates`).
"""

from http import HTTPStatus
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.admin import (
    AdminCreditRateDetails,
    AdminCreditRateUpdate,
    AdminTierDetails,
    AdminTierUpdate,
)
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.repositories.credit_package_rate_repo import (
    CreditPackageRateMutationRepository,
    CreditPackageRateRepository,
)
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.usecases.admin._audit import log_admin_action


async def list_tiers(session: AsyncSession) -> list[AdminTierDetails]:
    tiers = await SubscriptionRepository(session).admin_list_tiers()
    return [AdminTierDetails.model_validate(tier) for tier in tiers]


async def update_tier(
    session: AsyncSession,
    tier_id: UUID,
    payload: AdminTierUpdate,
    actor: AuthUserGrants,
) -> AdminTierDetails:
    repo = SubscriptionRepository(session)
    tier = await repo.get_subscription_tier_by_id(tier_id)
    if tier is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Subscription tier not found",
        )

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="No fields to update",
        )

    tier = await repo.update_tier(tier, fields)
    log_admin_action(
        actor, "tier.update", "subscription_tier", tier_id, fields=sorted(fields)
    )
    return AdminTierDetails.model_validate(tier)


async def list_credit_rates(
    session: AsyncSession, currency: str | None
) -> list[AdminCreditRateDetails]:
    rates = await CreditPackageRateRepository(session).get_all_rates(currency)
    return [AdminCreditRateDetails.model_validate(rate) for rate in rates]


async def update_credit_rate(
    session: AsyncSession,
    rate_id: UUID,
    payload: AdminCreditRateUpdate,
    actor: AuthUserGrants,
) -> AdminCreditRateDetails:
    query_repo = CreditPackageRateRepository(session)
    rate = await query_repo.get_rate_by_id(rate_id)
    if rate is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Credit package rate not found",
        )

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="No fields to update",
        )

    if fields.get("active") and not rate.active:
        conflicts = await query_repo.count_active_range_conflicts(
            currency=rate.currency,
            min_credits=rate.min_credits,
            exclude_rate_id=rate_id,
        )
        if conflicts:
            raise VliError(
                error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
                http_status_code=HTTPStatus.CONFLICT,
                message=(
                    "Another active rate already covers "
                    f"{rate.currency}/min_credits={rate.min_credits}"
                ),
            )

    rate = await CreditPackageRateMutationRepository(session).update_rate(rate, fields)
    log_admin_action(
        actor,
        "credit_rate.update",
        "credit_package_rate",
        rate_id,
        fields=sorted(fields),
    )
    return AdminCreditRateDetails.model_validate(rate)
