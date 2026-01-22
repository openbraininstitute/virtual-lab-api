import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, TypedDict
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    not_,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from virtual_labs.domain.bookmark import BookmarkCategory


# TypedDicts for JSON columns - defined here to avoid circular imports
class OnboardingStatusDict(TypedDict):
    """TypedDict for onboarding status stored in DB JSON"""

    completed: bool
    completed_at: Optional[str]
    current_step: Optional[int]
    dismissed: bool


class WorkspaceHierarchySpeciesPreferenceDict(TypedDict):
    """TypedDict for workspace hierarchy species preference stored in DB JSON"""

    hierarchy_id: str  # UUID stored as string in JSON
    species_name: str
    brain_region_id: Optional[str]  # UUID stored as string in JSON
    brain_region_name: Optional[str]


class Base(DeclarativeBase):
    pass


class ComputeCell(str, Enum):
    """Enum for available compute cells."""

    CELL_A = "cell_a"
    CELL_B = "cell_b"


class VirtualLab(Base):
    __tablename__ = "virtual_lab"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    admin_group_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    member_group_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    name: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    reference_email: Mapped[str | None] = mapped_column(String(255))
    entity: Mapped[str] = mapped_column(String, nullable=False)
    compute_cell: Mapped[ComputeCell] = mapped_column(
        SAEnum(ComputeCell),
        nullable=False,
        default=ComputeCell.CELL_A,
        server_default="CELL_A",
    )

    deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    projects = relationship("Project", back_populates="virtual_lab")
    invites = relationship("VirtualLabInvite", back_populates="virtual_lab")
    payment_methods = relationship("PaymentMethod", back_populates="virtual_lab")
    payments = relationship("SubscriptionPayment", back_populates="virtual_lab")

    __table_args__ = (
        Index(
            "unique_lab_name_for_non_deleted",
            name,
            deleted,
            unique=True,
            postgresql_where=(not_(deleted)),
        ),
    )

    @property
    def created_by(self) -> uuid.UUID:
        return self.owner_id


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    admin_group_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    member_group_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    virtual_lab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_lab.id"), nullable=False, index=True
    )
    virtual_lab = relationship("VirtualLab", back_populates="projects")
    project_stars = relationship("ProjectStar", back_populates="project")
    invites = relationship("ProjectInvite", back_populates="project")
    bookmarks = relationship("Bookmark", back_populates="project")

    __table_args__ = (
        Index(
            "unique_project_name_for_non_deleted",
            name,
            deleted,
            virtual_lab_id,
            unique=True,
            postgresql_where=(not_(deleted)),
        ),
    )


class ProjectStar(Base):
    __tablename__ = "project_star"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    user_id = Column(UUID, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id"), index=True)
    project = relationship("Project", back_populates="project_stars")


class ProjectInvite(Base):
    __tablename__ = "project_invite"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inviter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    user_email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id"), index=True, nullable=False
    )
    project: Mapped["Project"] = relationship("Project", back_populates="invites")


class VirtualLabInvite(Base):
    __tablename__ = "virtual_lab_invite"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inviter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    user_email: Mapped[str] = mapped_column(String, nullable=False)
    virtual_lab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_lab.id"), index=True, nullable=False
    )
    virtual_lab: Mapped["VirtualLab"] = relationship(
        "VirtualLab", back_populates="invites"
    )

    accepted: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )


class PaymentMethod(Base):
    __tablename__ = "payment_method"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_payment_method_id = Column(String, nullable=False)
    user_id = Column(UUID)

    default = Column(Boolean, default=False)
    card_number = Column(String(4), nullable=False)
    brand = Column(String, nullable=False)
    cardholder_name = Column(String, nullable=False)
    cardholder_email = Column(String, nullable=False)
    expire_at = Column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    virtual_lab_id = Column(
        "virtual_lab_id", UUID(as_uuid=True), ForeignKey("virtual_lab.id"), index=True
    )
    virtual_lab = relationship("VirtualLab", back_populates="payment_methods")

    __table_args__ = (
        Index(
            "ix_default_payment_per_lab",
            "virtual_lab_id",
            "default",
            unique=True,
            postgresql_where=(default.is_(True)),
        ),
    )


class Bookmark(Base):
    __tablename__ = "bookmark"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    category: Mapped[BookmarkCategory] = mapped_column(
        SAEnum(BookmarkCategory), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id"), index=True, nullable=False
    )
    project: Mapped["Project"] = relationship("Project", back_populates="bookmarks")

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "category",
            "project_id",
            name="bookmark_unique_for_resource_category_per_project",
        ),
    )


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    virtual_lab_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        # ensure the token is exactly 6 digits
        CheckConstraint("code ~* '^[0-9]{6}$'", name="valid_code_check"),
        # composite index for email and token
        Index(
            "ix_verification_codes_compound_properties",
            "email",
            "code",
            "virtual_lab_name",
            "user_id",
        ),
        Index("ix_verification_codes_created_at", "created_at"),
    )


class SubscriptionStatus(str, Enum):
    """
    Enum representing Stripe subscription statuses.
    ref: https://stripe.com/docs/api/subscriptions/object#subscription_object-status
    """

    ACTIVE = "active"  # the subscription is in good standing and the customer is being charged
    PAST_DUE = "past_due"  # payment failed but the subscription is still active
    UNPAID = "unpaid"  # payment failed and the subscription is no longer active
    CANCELED = "canceled"  # the subscription has been canceled
    INCOMPLETE = "incomplete"  # the subscription has not been fully created yet
    INCOMPLETE_EXPIRED = "incomplete_expired"  # the initial payment failed and the subscription was not created
    PAUSED = "paused"  # the subscription is paused


class SubscriptionType(str, Enum):
    """
    Enum representing subscription types.
    """

    FREE = "FREE"
    PRO = "PRO"
    PREMIUM = "PREMIUM"

    @classmethod
    def as_pg_enum(cls) -> SAEnum:
        return SAEnum(
            cls,
            name="subscriptiontype",
            create_type=True,  # This ensures the type is created in PostgreSQL
            native_enum=True,  # Use native PostgreSQL enum
            validate_strings=True,
        )


class SubscriptionSource(str, Enum):
    """
    Enum representing subscription source.
    """

    API = "api"
    SCRIPT = "script"
    SQL = "sql"


class PaymentStatus(str, Enum):
    """
    Enum representing Stripe payment statuses.
    """

    SUCCEEDED = "succeeded"
    PENDING = "pending"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class Subscription(Base):
    """
    Base subscription class containing common fields for all subscription types.
    Uses joined table inheritance pattern.
    """

    __tablename__ = "subscription"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    virtual_lab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_lab.id"), nullable=True, index=True
    )
    tier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_tier.id"), nullable=False
    )
    subscription_type: Mapped[str] = mapped_column(String(50))

    current_period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus), nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )

    # Discriminator column for inheritance
    type: Mapped[str] = mapped_column(String(50))
    # Source from where the subscription has been created
    source: Mapped[SubscriptionSource] = mapped_column(
        SAEnum(SubscriptionSource),
        nullable=False,
        default=SubscriptionSource.API,
        index=True,
    )

    # Relationships
    virtual_lab = relationship("VirtualLab")
    payments = relationship("SubscriptionPayment", back_populates="subscription")
    tier = relationship("SubscriptionTier", back_populates="subscriptions")
    __mapper_args__ = {"polymorphic_identity": "subscription", "polymorphic_on": "type"}

    __table_args__ = (
        Index("ix_subscription_status_period_end", "status", "current_period_end"),
    )


class FreeSubscription(Subscription):
    """
    Free tier subscription without any Stripe integration.
    """

    __tablename__ = "free_subscription"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription.id"), primary_key=True
    )

    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __mapper_args__ = {"polymorphic_identity": "free"}


class PaidSubscription(Subscription):
    """
    Paid subscription (Pro/Premium) with Stripe integration.
    """

    __tablename__ = "paid_subscription"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription.id"), primary_key=True
    )

    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    billing_cycle_anchor: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    default_payment_method: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    latest_invoice: Mapped[str | None] = mapped_column(String(255), nullable=True)

    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    interval: Mapped[str] = mapped_column(String(50), nullable=False)  # 'month', 'year'
    stripe_event: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)
    cancellation_reason: Mapped[str] = mapped_column(String(300), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "paid"}


class SubscriptionPayment(Base):
    """
    tracks individual payments for a subscription.
    each subscription will have multiple payments over time.
    it also track individual payments for a subscription.
    if the payment is for a standalone payment, the virtual lab should be not null.
    """

    __tablename__ = "subscription_payment"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription.id"), index=True
    )
    customer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    virtual_lab_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_lab.id"), nullable=True, index=True
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    stripe_payment_intent_id: Mapped[str] = mapped_column(
        String(255),
    )
    stripe_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    card_brand: Mapped[str] = mapped_column(String(50), nullable=False)
    card_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    card_exp_month: Mapped[int] = mapped_column(Integer, nullable=False)
    card_exp_year: Mapped[int] = mapped_column(Integer, nullable=False)

    amount_paid: Mapped[int] = mapped_column(Integer, nullable=False)  # Amount in cents
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), nullable=False, index=True
    )

    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    payment_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    invoice_pdf: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )
    stripe_event: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)
    standalone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription = relationship("Subscription", back_populates="payments")
    virtual_lab = relationship("VirtualLab", back_populates="payments")

    @property
    def card_exp(self) -> str:
        """Returns card expiration date in MM/YY format."""
        return f"{self.card_exp_month:02d}/{str(self.card_exp_year)[-2:]}"

    __table_args__ = (
        CheckConstraint(
            "NOT standalone OR virtual_lab_id IS NOT NULL",
            name="check_virtual_lab_required_when_standalone",
        ),
    )


class SubscriptionTierEnum(str, Enum):
    """
    Enum representing subscription tiers.
    """

    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"


class SubscriptionTier(Base):
    """
    app plans
    """

    __tablename__ = "subscription_tier"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    tier: Mapped[SubscriptionTierEnum] = mapped_column(
        SAEnum(SubscriptionTierEnum), nullable=False, index=True
    )
    stripe_product_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sanity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    stripe_monthly_price_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    monthly_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_discount: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    stripe_yearly_price_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    yearly_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yearly_discount: Mapped[int] = mapped_column(Integer, nullable=True, default=0)

    features: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    plan_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    subscriptions = relationship("Subscription", back_populates="tier")

    monthly_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yearly_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )


class StripeUser(Base):
    """
    user stripe customer id
    """

    __tablename__ = "stripe_user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=False, unique=True
    )
    user_id = Column(UUID(as_uuid=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )


class CreditExchangeRate(Base):
    __tablename__ = "credit_exchange_rate"

    currency: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class UserPreference(Base):
    """
    User preferences table for storing recent workspace information.
    Uses separate foreign key columns for better performance and data integrity.
    """

    __tablename__ = "user_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    virtual_lab_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_lab.id"), nullable=True, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    virtual_lab = relationship("VirtualLab", foreign_keys=[virtual_lab_id])
    project = relationship("Project", foreign_keys=[project_id])

    onboarding_progress: Mapped[Dict[str, OnboardingStatusDict]] = mapped_column(
        JSON, default={}, server_default="{}"
    )

    workspace_hierarchy_species: Mapped[
        Optional[WorkspaceHierarchySpeciesPreferenceDict]
    ] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_user_preference_workspace", "virtual_lab_id", "project_id"),
    )


class PromotionCodeUsageStatus(str, Enum):
    """
    Enum representing promotion code usage statuses.
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class PromotionCode(Base):
    """
    Promotion code definitions and configurations.
    Stores all promotion codes that can be redeemed for virtual lab credits.
    """

    __tablename__ = "promotion_code"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credits_amount: Mapped[float] = mapped_column(Float, nullable=False)
    validity_period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses_per_user_per_period: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    max_total_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_total_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )

    usages = relationship("PromotionCodeUsage", back_populates="promotion_code")

    __table_args__ = (
        CheckConstraint("valid_until > valid_from", name="check_valid_date_range"),
        CheckConstraint("credits_amount > 0", name="check_positive_credits"),
        CheckConstraint(
            "max_total_uses IS NULL OR max_total_uses > 0",
            name="check_positive_max_uses",
        ),
        CheckConstraint(
            "max_uses_per_user_per_period > 0",
            name="check_positive_user_period_uses",
        ),
        Index("ix_promotion_code_validity", "active", "valid_from", "valid_until"),
    )


class PromotionCodeUsage(Base):
    """
    Audit and tracking table for promotion code redemptions.
    Records every successful redemption with complete audit trail.
    """

    __tablename__ = "promotion_code_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    promotion_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("promotion_code.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    virtual_lab_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_lab.id"), nullable=False, index=True
    )
    credits_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    accounting_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[PromotionCodeUsageStatus] = mapped_column(
        SAEnum(PromotionCodeUsageStatus), nullable=False, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )

    promotion_code = relationship("PromotionCode", back_populates="usages")
    virtual_lab = relationship("VirtualLab")

    __table_args__ = (
        CheckConstraint("credits_granted > 0", name="check_positive_credits_granted"),
        Index(
            "ix_promotion_usage_user_code_date",
            "user_id",
            "promotion_code_id",
            "redeemed_at",
        ),
        Index("ix_promotion_usage_code_status", "promotion_code_id", "status"),
        Index("ix_promotion_usage_lab_date", "virtual_lab_id", "redeemed_at"),
    )


class PromotionCodeRedemptionAttempt(Base):
    """
    Analytics table tracking all redemption attempts.
    Used for analytics and user behavior tracking.
    """

    __tablename__ = "promotion_code_redemption_attempt"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    code_attempted: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    virtual_lab_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_promotion_attempt_user_time", "user_id", "attempted_at"),
        Index("ix_promotion_attempt_code_time", "code_attempted", "attempted_at"),
    )
