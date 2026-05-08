from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class BillingFlow(str, Enum):
    STANDALONE = "standalone"
    SUBSCRIPTION = "subscription"


class TaxBehavior(str, Enum):
    EXCLUSIVE = "exclusive"


class TaxStatus(str, Enum):
    CALCULATED = "calculated"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    FAILED = "failed"


class BillingAddress(BaseModel):
    name: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = Field(..., min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.upper()


class CreateBillingQuoteRequest(BaseModel):
    flow: BillingFlow
    billing_address: BillingAddress
    currency: str = Field("chf", min_length=3, max_length=3)
    virtual_lab_id: Optional[UUID] = None
    credits: Optional[int] = Field(default=None, gt=0)
    tier_id: Optional[UUID] = None
    interval: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_flow_payload(self) -> "CreateBillingQuoteRequest":
        if self.flow == BillingFlow.STANDALONE:
            if self.virtual_lab_id is None or self.credits is None:
                raise ValueError("standalone quotes require virtual_lab_id and credits")
        if self.flow == BillingFlow.SUBSCRIPTION:
            if self.tier_id is None or self.interval is None:
                raise ValueError("subscription quotes require tier_id and interval")
        return self


class BillingQuoteResponse(BaseModel):
    quote_id: UUID
    flow: BillingFlow
    subtotal: int
    tax_amount: int
    total: int
    currency: str
    tax_behavior: TaxBehavior
    tax_country: Optional[str] = None
    tax_status: TaxStatus
    expires_at: datetime


class CreditConversionRequest(BaseModel):
    credits: int = Field(..., gt=0)
    currency: str = Field("chf", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.lower()


class CreditConversionResponse(BaseModel):
    credits: int
    currency: str
    amount: int
    rate: Decimal
