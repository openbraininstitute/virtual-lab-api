from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from virtual_labs.domain.billing import BillingAddress


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
    amount_subtotal: Optional[int] = None
    amount_tax: Optional[int] = None
    amount_total: Optional[int] = None
    currency: str
    tax_country: Optional[str] = None
    tax_behavior: Optional[str] = None
    tax_status: Optional[str] = None
    credits_purchased: Optional[int] = None
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

    @classmethod
    def build(
        cls,
        payments: List[PaymentDetails],
        *,
        total: int,
        page: int,
        page_size: int,
    ) -> "PaymentListResponse":
        """Derive the pagination envelope from one page of items."""
        total_pages = (total + page_size - 1) // page_size
        return cls(
            total_count=total,
            total_pages=total_pages,
            current_page=page,
            page_size=page_size,
            has_next=page < total_pages,
            has_previous=page > 1,
            payments=payments,
        )


class CreateStandalonePaymentRequest(BaseModel):
    """
    creating a standalone payment
    """

    quote_id: UUID = Field(..., description="billing quote id")
    payment_method_id: str = Field(..., description="stripe payment method id")
    virtual_lab_id: UUID = Field(..., description="virtual lab id")
    billing_address: BillingAddress = Field(..., description="billing address")
    sync_billing_address_to_profile: bool = Field(
        default=True, description="whether to save billing address to user profile"
    )
