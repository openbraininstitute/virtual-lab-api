import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
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


class Base(DeclarativeBase):
    pass


class VirtualLab(Base):
    __tablename__ = "virtual_lab"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    admin_group_id = Column(String, nullable=False, unique=True)
    member_group_id = Column(String, nullable=False, unique=True)

    nexus_organization_id = Column(String, nullable=False, unique=True)

    name = Column(String(250), index=True)
    description = Column(Text)
    reference_email = Column(String(255))
    entity = Column(String, nullable=False)

    deleted = Column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
    deleted_at = Column(DateTime)
    deleted_by = Column(UUID(as_uuid=True))

    projects = relationship("Project", back_populates="virtual_lab")
    invites = relationship("VirtualLabInvite", back_populates="virtual_lab")
    payment_methods = relationship("PaymentMethod", back_populates="virtual_lab")
    payments = relationship("SubscriptionPayment", back_populates="virtual_lab")
    # Virtual lab name should be unique among non-deleted labs
    __table_args__ = (
        Index(
            "unique_lab_name_for_non_deleted",
            name,
            deleted,
            unique=True,
            postgresql_where=(not_(deleted)),
        ),
    )


class Project(Base):
    __tablename__ = "project"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nexus_project_id = Column(String, nullable=False, unique=True)
    admin_group_id = Column(String, nullable=False, unique=True)
    member_group_id = Column(String, nullable=False, unique=True)
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(250), index=True)
    description = Column(Text)
    deleted = Column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
    deleted_at = Column(DateTime)
    deleted_by = Column(UUID(as_uuid=True))

    virtual_lab_id = Column(
        "virtual_lab_id", UUID(as_uuid=True), ForeignKey("virtual_lab.id"), index=True
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True))
    accepted = Column(Boolean, default=False)
    user_email = Column(String, nullable=False)
    role = Column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"), index=True)
    project = relationship("Project", back_populates="invites")


class VirtualLabInvite(Base):
    __tablename__ = "virtual_lab_invite"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id = Column(UUID, nullable=False)
    user_id = Column(UUID)
    role = Column(String, nullable=False)
    user_email = Column(String, nullable=False)
    virtual_lab_id = Column(UUID, ForeignKey("virtual_lab.id"), index=True)
    virtual_lab = relationship("VirtualLab", back_populates="invites")

    accepted = Column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id = Column(String, nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        unique=False, index=True, nullable=True
    )
    category = Column(SAEnum(BookmarkCategory), nullable=False)  # type: ignore[var-annotated]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id"), index=True)
    project = relationship("Project", back_populates="bookmarks")

    __table_args__ = (
        UniqueConstraint(
            resource_id,
            category,
            project_id,
            name="bookmark_unique_for_resource_category_per_project",
        ),
    )


class Notebook(Base):
    __tablename__ = "notebook"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project.id"), index=True
    )
    github_file_url: Mapped[str] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "github_file_url", name="uq_project_file_url"),
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
