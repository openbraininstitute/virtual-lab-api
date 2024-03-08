import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
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
    deleted = Column(Boolean, default=False, index=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime)

    projects = relationship("Project", back_populates="virtual_lab")


class Project(Base):
    __tablename__ = "project"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nexus_project_id = Column(
        String(255), nullable=False, unique=True
    )  # the string length may change in the future, when we know the structure of it

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


# class Invite(Base):
#     __tablename__ = "invite"

#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

#     invitee = Column(UUID(as_uuid=True))
#     inviter = Column(String)

#     created_at = Column(DateTime, default=datetime.utcnow)
#     updated_at = Column(DateTime, onupdate=datetime.utcnow)

#     virtual_lab_id = Column(
#         "virtual_lab_id", UUID(as_uuid=True), ForeignKey("virtual_lab.id")
#     )
#     virtual_lab = relationship("VirtualLab")

#     project_id = Column("project_id", UUID(as_uuid=True), ForeignKey("project.id"))
#     project = relationship("Project")
