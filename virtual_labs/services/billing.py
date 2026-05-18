from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.billing import (
    BillingAddress,
    BillingFlow,
    BillingQuoteResponse,
    CreateBillingQuoteRequest,
    TaxBehavior,
    TaxStatus,
)
from virtual_labs.infrastructure.db.models import BillingQuote
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.credit_package_rate_repo import (
    CreditPackageRateRepository,
)
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)
from virtual_labs.services.credit_converter import CreditConverter


def billing_address_to_profile_attributes(
    address: BillingAddress,
) -> dict[str, list[str]]:
    attrs = {
        "country": address.country,
        "street": address.line1,
        "postal_code": address.postal_code,
        "locality": address.city,
        "region": address.state,
    }
    return {key: [value] for key, value in attrs.items() if value}


def billing_address_to_stripe(address: BillingAddress) -> dict[str, str]:
    stripe_address = {
        "line1": address.line1,
        "line2": address.line2,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "country": address.country,
    }
    return {key: value for key, value in stripe_address.items() if value}


# Keycloak enforces a single-value validator on these attributes. We resend
# them as a one-element list (taking the first value when the existing record
# happens to have several) so the update preserves them without triggering
# the 400 from the validator.
_SINGLE_VALUE_ATTRIBUTES: frozenset[str] = frozenset({"plan"})


def _normalize_kc_attributes(
    attributes: dict[str, Any],
) -> dict[str, list[str]]:
    """Coerce Keycloak attribute values into the list-of-strings shape that
    `a_update_user` expects, preserving everything currently set.

    Special-cases `_SINGLE_VALUE_ATTRIBUTES` to a single-element list so the
    update doesn't trip Keycloak's single-value validator on those keys.
    """
    normalized: dict[str, list[str]] = {}
    for key, value in attributes.items():
        if isinstance(value, list):
            values = [str(v) for v in value if v is not None]
        elif value is None:
            continue
        else:
            values = [str(value)]
        if not values:
            continue
        if key in _SINGLE_VALUE_ATTRIBUTES:
            values = values[:1]
        normalized[key] = values
    return normalized


async def save_billing_address_to_user_profile(
    *,
    user_id: UUID,
    address: BillingAddress,
) -> None:
    user_query_repo = UserQueryRepository()
    user_mutation_repo = UserMutationRepository()
    kc_user = await user_query_repo.get_user(user_id=str(user_id))
    attributes = kc_user.get("attributes", {}) if kc_user else {}

    # `a_update_user` overwrites the full `attributes` map — every existing
    # attribute (including `plan`) must be re-sent, otherwise Keycloak drops it.
    merged_attributes = _normalize_kc_attributes(attributes)
    merged_attributes.update(billing_address_to_profile_attributes(address))

    await user_mutation_repo.Kc.a_update_user(
        user_id=str(user_id),
        payload={
            "email": kc_user.get("email"),
            "firstName": kc_user.get("firstName"),
            "lastName": kc_user.get("lastName"),
            "attributes": merged_attributes,
        },
    )


def is_tax_enabled_for_country(country: str | None) -> bool:
    if not settings.BILLING_TAX_ENABLED or not country:
        return False
    enabled_countries = {
        value.strip().upper()
        for value in settings.BILLING_TAX_ENABLED_COUNTRIES.split(",")
        if value.strip()
    }
    return country.upper() in enabled_countries


def _extract_tax_amount(tax_calculation: dict[str, Any], subtotal: int) -> int:
    invoice_tax = tax_calculation.get("tax")
    if invoice_tax is not None:
        return int(invoice_tax)
    total_tax_amounts = tax_calculation.get("total_tax_amounts")
    if isinstance(total_tax_amounts, list):
        return sum(
            int(item.get("amount", 0) or 0)
            for item in total_tax_amounts
            if isinstance(item, dict)
        )
    for key in ("tax_amount_exclusive", "amount_tax"):
        value = tax_calculation.get(key)
        if value is not None:
            return int(value)
    amount_total = tax_calculation.get("amount_total")
    if amount_total is not None:
        return max(int(amount_total) - subtotal, 0)
    return 0


def quote_expires_at_end_of_today(now: datetime | None = None) -> datetime:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    utc_time = current_time.astimezone(timezone.utc)
    return utc_time.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999,
    )


class BillingQuoteService:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session
        self.stripe = get_stripe_repository()
        self.subscription_repo = SubscriptionRepository(db_session=session)
        self.credit_converter = CreditConverter(
            package_rate_repo=CreditPackageRateRepository(session=session)
        )

    async def create_quote(
        self,
        payload: CreateBillingQuoteRequest,
        user_id: UUID,
    ) -> BillingQuote:
        subtotal, discount_pct, credit_package_rate_id = await self._resolve_subtotal(
            payload
        )
        tax_amount = 0
        total = subtotal
        tax_status = TaxStatus.NOT_APPLICABLE
        stripe_tax_calculation_id = None

        if is_tax_enabled_for_country(payload.billing_address.country):
            tax_calculation = await self.stripe.create_tax_calculation(
                amount=subtotal,
                currency=payload.currency,
                address=payload.billing_address,
                reference=f"{payload.flow}:{user_id}",
                tax_code=settings.STRIPE_CREDIT_TAX_CODE
                if payload.flow == BillingFlow.STANDALONE
                else None,
            )
            tax_calculation_dict = dict(tax_calculation)
            tax_amount = _extract_tax_amount(tax_calculation_dict, subtotal)
            total = int(tax_calculation_dict.get("amount_total", subtotal + tax_amount))
            tax_status = TaxStatus.CALCULATED
            stripe_tax_calculation_id = tax_calculation_dict.get("id")

        quote = BillingQuote(
            user_id=user_id,
            virtual_lab_id=payload.virtual_lab_id,
            flow=payload.flow,
            subscription_tier_id=payload.tier_id,
            interval=payload.interval,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
            currency=payload.currency,
            tax_behavior=TaxBehavior(settings.BILLING_TAX_BEHAVIOR),
            tax_country=payload.billing_address.country,
            tax_status=tax_status,
            billing_address_json=payload.billing_address.model_dump(),
            stripe_tax_calculation_id=stripe_tax_calculation_id,
            discount_pct=discount_pct,
            credit_package_rate_id=credit_package_rate_id,
            expires_at=quote_expires_at_end_of_today(),
        )
        self.session.add(quote)
        await self.session.commit()
        await self.session.refresh(quote)
        return quote

    async def get_valid_quote(
        self,
        quote_id: UUID,
        user_id: UUID,
        flow: BillingFlow,
        virtual_lab_id: UUID | None = None,
        subscription_tier_id: UUID | None = None,
        interval: str | None = None,
    ) -> BillingQuote | None:
        stmt = select(BillingQuote).where(
            BillingQuote.id == quote_id,
            BillingQuote.user_id == user_id,
            BillingQuote.flow == flow,
            BillingQuote.expires_at > datetime.now(timezone.utc),
        )
        if virtual_lab_id is not None:
            stmt = stmt.where(BillingQuote.virtual_lab_id == virtual_lab_id)
        if subscription_tier_id is not None:
            stmt = stmt.where(BillingQuote.subscription_tier_id == subscription_tier_id)
        if interval is not None:
            stmt = stmt.where(BillingQuote.interval == interval)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _resolve_subtotal(
        self, payload: CreateBillingQuoteRequest
    ) -> tuple[int, int, UUID | None]:
        """Resolve the subtotal amount, discount percentage, and rate tier ID.

        Returns:
            (subtotal_in_cents, discount_pct, credit_package_rate_id)
        """
        if payload.flow == BillingFlow.STANDALONE:
            assert payload.credits is not None
            result = await self.credit_converter.convert_credits(
                payload.credits,
                payload.currency,
            )
            return result.amount, result.discount_pct, result.credit_package_rate_id

        assert payload.tier_id is not None
        tier = await self.subscription_repo.get_subscription_tier_by_id(payload.tier_id)
        if tier is None:
            raise ValueError("Subscription plan not found")
        if payload.interval == "year":
            return tier.yearly_amount, 0, None
        return tier.monthly_amount, 0, None


def quote_to_response(quote: BillingQuote) -> BillingQuoteResponse:
    return BillingQuoteResponse(
        quote_id=quote.id,
        flow=quote.flow
        if isinstance(quote.flow, BillingFlow)
        else BillingFlow(quote.flow),
        subtotal=quote.subtotal,
        tax_amount=quote.tax_amount,
        total=quote.total,
        currency=quote.currency,
        tax_behavior=(
            quote.tax_behavior
            if isinstance(quote.tax_behavior, TaxBehavior)
            else TaxBehavior(quote.tax_behavior)
        ),
        tax_country=quote.tax_country,
        tax_status=(
            quote.tax_status
            if isinstance(quote.tax_status, TaxStatus)
            else TaxStatus(quote.tax_status)
        ),
        expires_at=quote.expires_at,
    )
