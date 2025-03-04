import uuid
from datetime import datetime
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


class VirtualLabTopup(Base):
    __tablename__ = "virtual_lab_topup"

    id: Mapped[int] = mapped_column(primary_key=True)
    virtual_lab_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("virtual_lab.id"), index=True
    )
    amount: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    stripe_event_id: Mapped[str] = mapped_column()


class VirtualLab(Base):
    __tablename__ = "virtual_lab"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    admin_group_id = Column(String, nullable=False, unique=True)
    member_group_id = Column(String, nullable=False, unique=True)

    nexus_organization_id = Column(String, nullable=False, unique=True)
    stripe_customer_id = Column(String, nullable=False, unique=True)

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


# TODO: Remove this table in subscription migration
class Plan(Base):
    __tablename__ = "plan"

    id = Column(Integer, primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True, index=True)
    price = Column(Float, nullable=False)
    features = Column(JSON, nullable=False)


class ProjectInvite(Base):
    __tablename__ = "project_invite"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inviter_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True))
    accepted = Column(Boolean)
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
    resource_id = Column(String, nullable=False, index=True)

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
