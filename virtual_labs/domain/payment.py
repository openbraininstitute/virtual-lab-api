from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentType(str, Enum):
    SUBSCRIPTION = "subscription"
    STANDALONE = "standalone"


class PaymentFilter(BaseModel):
    """
    filter criteria for listing payments
    """

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    payment_type: Optional[PaymentType] = None
    virtual_lab_id: Optional[UUID] = None

    # Pagination parameters
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(
        default=10, ge=1, le=100, description="Number of items per page"
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaymentDetails(BaseModel):
    """
    Payment details response model
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount_paid: int
    currency: str
    status: str
    payment_date: datetime
    payment_type: PaymentType

    # Card details
    card_brand: str
    card_last4: str
    card_exp_month: int
    card_exp_year: int

    # Receipt info
    receipt_url: Optional[str] = None
    invoice_pdf: Optional[str] = None

    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    virtual_lab_id: Optional[UUID] = None

    created_at: datetime
    updated_at: datetime


class PaymentListResponse(BaseModel):
    """
    Response model for payment listing
    """

    total_count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_previous: bool
    payments: List[PaymentDetails]


class CreateStandalonePaymentRequest(BaseModel):
    """
    creating a standalone payment
    """

    amount: int = Field(..., description="Amount to charge in cents")
    currency: str = Field("usd", description="Currency code (e.g., 'chf')")
    payment_method_id: str = Field(..., description="stripe payment method id")
    virtual_lab_id: UUID = Field(..., description="virtual lab id")
