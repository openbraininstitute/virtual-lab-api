import uuid

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
    not_,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class VirtualLab(Base):
    __tablename__ = "virtual_lab"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nexus_organization_id = Column(
        String(255), nullable=False, unique=True
    )  # the string length may change in the future, when we know the structure of it
    name = Column(String(250), unique=True, index=True)
    description = Column(Text)
    reference_email = Column(String(255))

    budget = Column(
        Float(2), CheckConstraint("budget > 0"), nullable=False
    )  # Amount in USD

    deleted = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime)

    projects = relationship("Project", back_populates="virtual_lab")
    invites = relationship("VirtualLabInvite", back_populates="virtual_lab")

    plan_id = Column(Integer, ForeignKey("plan.id"))
    plan = relationship("Plan", back_populates="virtual_labs")


class Project(Base):
    __tablename__ = "project"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nexus_project_id = Column(String, nullable=False, unique=True)
    kc_project_group_id = Column(String, nullable=False, unique=True)
    name = Column(String(250), index=True)
    description = Column(Text)
    deleted = Column(Boolean, default=False)
    budget = Column(Float, default=None)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), default=func.now())
    deleted_at = Column(DateTime)

    virtual_lab_id = Column(
        "virtual_lab_id", UUID(as_uuid=True), ForeignKey("virtual_lab.id")
    )
    virtual_lab = relationship("VirtualLab", back_populates="projects")
    project_stars = relationship("ProjectStar", back_populates="project")
    invites = relationship("ProjectInvite", back_populates="project")

    __table_args__ = (
        Index(
            "unique_name_for_non_deleted",
            name,
            deleted,
            unique=True,
            postgresql_where=(not_(deleted)),
        ),
    )


class ProjectStar(Base):
    __tablename__ = "project_star"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=func.now())

    user_id = Column(UUID, nullable=False)
    project_id = Column(UUID, ForeignKey("project.id"))
    project = relationship("Project", back_populates="project_stars")


class Plan(Base):
    __tablename__ = "plan"

    id = Column(Integer, primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True, index=True)
    price = Column(Float(2), nullable=False)
    features = Column(JSON, nullable=False)
    virtual_labs = relationship("VirtualLab", back_populates="plan")


class ProjectInvite(Base):
    __tablename__ = "project_invite"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email = Column(String, nullable=False)
    user_id = Column(UUID)
    competed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), default=func.now())

    project_id = Column(UUID, ForeignKey("project.id"))
    project = relationship("Project", back_populates="invites")


class VirtualLabInvite(Base):
    __tablename__ = "virtual_lab_invite"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email = Column(String, nullable=False)
    user_id = Column(UUID)
    competed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), default=func.now())

    virtual_lab_id = Column(UUID, ForeignKey("virtual_lab.id"))
    virtual_lab = relationship("VirtualLab", back_populates="invites")


# class PaymentCard(Base):
#     __tablename__ = "payment_card"

#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     cardNumber = Column(String(19))
#     expiration_date = Column(DateTime)

#     created_at = Column(DateTime, default=datetime.utcnow)
#     updated_at = Column(DateTime, onupdate=datetime.utcnow)

#     virtual_lab_id = Column(
#         "virtual_lab_id", UUID(as_uuid=True), ForeignKey("virtual_lab.id")
#     )
#     virtual_lab = relationship("VirtualLab")


# class Billing(Base):
#     __tablename__ = "billing"

#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

#     payment_card_id = Column(
#         "payment_card_id", UUID(as_uuid=True), ForeignKey("payment_card.id")
#     )
#     payment_card = relationship("PaymentCard")
