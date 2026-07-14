"""Request/response models for the platform-admin (`/admin`) namespace.

List endpoints paginate with `PaginationRequest` query params and
respond with `PaginatedResponse[T]`. Detail models extend the
user-facing domain models with the operator-only columns (ownership,
soft-delete state) that member-scoped endpoints deliberately omit.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field

from virtual_labs.domain.common import OrderDirection, PaginationRequest
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.payment import PaymentFilter
from virtual_labs.domain.project import Project
from virtual_labs.domain.subscription import SubscriptionDetails
from virtual_labs.infrastructure.db.models import (
    SubscriptionStatus,
    SubscriptionTierEnum,
)
from virtual_labs.infrastructure.kc.models import UserRepresentation

# ---------------------------------------------------------------------------
# Shared query axes
# ---------------------------------------------------------------------------


class AdminOrderBy(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    NAME = "name"


class DeletedScopedQuery(PaginationRequest):
    """Soft-delete visibility axis shared by lab/project listings.

    Default surfaces live rows only; `include_deleted` widens to both;
    `deleted_only` narrows to the trash view (and wins over
    `include_deleted`).
    """

    include_deleted: bool = False
    deleted_only: bool = False


# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------


class AdminLabsListQuery(DeletedScopedQuery):
    query: str | None = Field(default=None, min_length=1, max_length=200)
    order_by: AdminOrderBy = AdminOrderBy.UPDATED_AT
    order_direction: OrderDirection = OrderDirection.DESC


class AdminVirtualLabDetails(VirtualLabDetails):
    owner_id: UUID4
    deleted: bool
    deleted_at: datetime | None = None
    deleted_by: UUID4 | None = None


class AdminLabInviteDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    user_email: str
    role: str
    inviter_id: UUID4
    user_id: UUID4 | None = None
    accepted: bool | None = None
    created_at: datetime
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class AdminProjectsListQuery(DeletedScopedQuery):
    query: str | None = Field(default=None, min_length=1, max_length=200)
    virtual_lab_id: UUID4 | None = None
    order_by: AdminOrderBy = AdminOrderBy.UPDATED_AT
    order_direction: OrderDirection = OrderDirection.DESC


class AdminProjectDetails(Project):
    virtual_lab_id: UUID4
    virtual_lab_name: str | None = None
    owner_id: UUID4
    deleted: bool
    deleted_at: datetime | None = None
    deleted_by: UUID4 | None = None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class AdminUsersListQuery(PaginationRequest):
    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Keycloak search over username, email and name",
    )


class AdminUserVlabMembership(BaseModel):
    id: UUID4
    name: str | None = None
    role: str


class AdminUserProjectMembership(BaseModel):
    id: UUID4
    name: str | None = None
    virtual_lab_id: UUID4 | None = None
    role: str


class AdminUserDetails(BaseModel):
    user: UserRepresentation
    groups: list[str]
    virtual_labs: list[AdminUserVlabMembership]
    projects: list[AdminUserProjectMembership]


# ---------------------------------------------------------------------------
# Subscriptions & payments
# ---------------------------------------------------------------------------


class AdminSubscriptionsListQuery(PaginationRequest):
    status: SubscriptionStatus | None = None
    subscription_type: str | None = Field(
        default=None, description="Subscription type: `free` or `paid`"
    )
    user_id: UUID4 | None = None
    virtual_lab_id: UUID4 | None = None


class AdminSubscriptionDetails(SubscriptionDetails):
    user_id: UUID4
    virtual_lab_id: UUID4 | None = None
    tier: str | None = None


class AdminPaymentsListQuery(PaymentFilter):
    """`PaymentFilter` plus a user filter, as one query model.

    A single model on purpose: FastAPI silently stops exploding a
    query-parameter model when a plain scalar query param sits next to
    it in the signature — the model becomes one required `filters`
    param.
    """

    user_id: UUID4 | None = None


# ---------------------------------------------------------------------------
# Plans (subscription tiers) & credit package rates
# ---------------------------------------------------------------------------


class AdminTierDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # plain UUID: seeded tiers use fixed, non-v4 ids
    id: UUID
    tier: SubscriptionTierEnum
    name: str
    description: str | None = None
    active: bool
    currency: str
    stripe_product_id: str | None = None
    stripe_monthly_price_id: str | None = None
    monthly_amount: int
    monthly_discount: int | None = None
    stripe_yearly_price_id: str | None = None
    yearly_amount: int
    yearly_discount: int | None = None
    monthly_credits: int
    yearly_credits: int
    features: dict[str, Any] | None = None
    plan_metadata: dict[str, Any] | None = None
    sanity_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminTierUpdate(BaseModel):
    """Editable tier fields. Stripe ids are read-only through the
    admin API — they change via the Stripe-driven seeding script."""

    name: str | None = None
    description: str | None = None
    active: bool | None = None
    features: dict[str, Any] | None = None
    monthly_credits: int | None = Field(default=None, ge=0)
    yearly_credits: int | None = Field(default=None, ge=0)
    monthly_discount: int | None = Field(default=None, ge=0)
    yearly_discount: int | None = Field(default=None, ge=0)


class AdminCreditRateDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # plain UUID for consistency with AdminTierDetails
    id: UUID
    currency: str
    min_credits: int
    max_credits: int | None = None
    rate: Decimal
    discount_pct: int
    active: bool
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminCreditRateUpdate(BaseModel):
    rate: Decimal | None = Field(default=None, gt=0)
    discount_pct: int | None = Field(default=None, ge=0, le=100)
    max_credits: int | None = Field(default=None, gt=0)
    active: bool | None = None
