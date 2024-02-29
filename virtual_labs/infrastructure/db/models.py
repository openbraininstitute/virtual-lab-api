import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Null,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship

from virtual_labs.core.exceptions.api_error import VlmError, VlmErrorCode
from virtual_labs.infrastructure.settings import settings

if settings.DATABASE_URI is None:
    raise VlmError(
        "DATABASE_URI/DATABASE_URL is not set",
        error_code=VlmErrorCode.DATABASE_URI_NOT_SET,
    )


class Base(DeclarativeBase):
    pass


class VirtualLab(Base):
    __tablename__ = "virtual_lab"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nexus_organization_id = Column(
        String(255), nullable=False
    )  # the string length may change in the future, when we know the structure of it
    name = Column(String(250), unique=True)
    description = Column(Text, default=String(""))
    deleted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, default=Null)


class Project(Base):
    __tablename__ = "project"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nexus_project_id = Column(
        String(255), nullable=False
    )  # the string length may change in the future, when we know the structure of it

    name = Column(String(250), unique=True)
    description = Column(Text, default=String(""))
    deleted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, default=Null)

    virtual_lab_id = Column(
        "virtual_lab_id", UUID(as_uuid=True), ForeignKey("virtual_lab.id")
    )
    virtual_lab = relationship("Project")


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
