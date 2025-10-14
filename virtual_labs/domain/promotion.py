"""
Domain models for promotion code system.
Defines Pydantic schemas for validation, serialization, and API contracts.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from virtual_labs.infrastructure.db.models import PromotionCodeUsageStatus


class PromotionCodeCreate(BaseModel):
    """
    Schema for creating a new promotion code.

    Note: Duplicate codes are allowed with different validity periods.
    This enables tracking seasonal/yearly campaigns (e.g., WELCOME100 in 2025, 2026, etc.)
    """

    code: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Promotion code (e.g., OBI2025). Duplicates allowed with different validity periods.",
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Human-readable description"
    )
    credits_amount: int = Field(
        ..., gt=0, description="Amount of credits to grant upon redemption"
    )
    validity_period_days: int = Field(
        ..., gt=0, description="Number of days the code remains valid"
    )
    max_uses_per_user_per_period: int = Field(
        default=1,
        gt=0,
        description="How many times a user can use this code per validity period",
    )
    max_total_uses: Optional[int] = Field(
        None,
        gt=0,
        description="Total redemption limit across all users (None = unlimited)",
    )
    active: bool = Field(default=True, description="Whether the code is active")
    valid_from: datetime = Field(..., description="Start date of validity period")
    valid_until: datetime = Field(..., description="End date of validity period")

    @field_validator("valid_until")
    @classmethod
    def validate_date_range(cls, v: datetime, info: ValidationInfo) -> datetime:
        """Ensure valid_until is after valid_from."""
        if info.data and "valid_from" in info.data and v <= info.data["valid_from"]:
            raise ValueError("valid_until must be after valid_from")
        return v

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        """Ensure code is uppercase and alphanumeric."""
        return v.upper().strip()


class PromotionCodeUpdate(BaseModel):
    """Schema for updating an existing promotion code (limited fields for safety)."""

    description: Optional[str] = Field(None, max_length=1000)
    active: Optional[bool] = None
    valid_until: Optional[datetime] = None
    max_total_uses: Optional[int] = Field(None, gt=0)


class RedeemPromotionCodeRequest(BaseModel):
    """Schema for redeeming a promotion code."""

    code: str = Field(..., min_length=1, max_length=50, description="Promotion code")
    virtual_lab_id: UUID = Field(..., description="Virtual lab to receive credits")

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        """Normalize code to uppercase."""
        return v.upper().strip()


class PromotionCodeOut(BaseModel):
    """Basic promotion code output schema."""

    id: UUID
    code: str
    description: Optional[str]
    credits_amount: int
    validity_period_days: int
    max_uses_per_user_per_period: int
    max_total_uses: Optional[int]
    current_total_uses: int
    active: bool
    valid_from: datetime
    valid_until: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromotionCodeDetail(PromotionCodeOut):
    """Detailed promotion code output with additional admin fields."""

    created_by: Optional[UUID]

    model_config = {"from_attributes": True}


class PromotionCodeUsageOut(BaseModel):
    """Promotion code usage/redemption output schema."""

    id: UUID
    promotion_code_id: UUID
    promotion_code: str
    user_id: UUID
    virtual_lab_id: UUID
    virtual_lab_name: Optional[str] = None
    credits_granted: int
    status: PromotionCodeUsageStatus
    redeemed_at: datetime
    accounting_transaction_id: Optional[str]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class RedemptionResult(BaseModel):
    """Result of a promotion code redemption."""

    redemption_id: UUID
    promotion_code: str
    credits_granted: int
    virtual_lab_id: UUID
    status: PromotionCodeUsageStatus
    redeemed_at: datetime
    accounting_transaction_id: Optional[str] = None


class PromotionCodeStatistics(BaseModel):
    """Usage statistics for a promotion code."""

    total_redemptions: int = 0
    completed: int = 0
    pending: int = 0
    failed: int = 0
    rolled_back: int = 0
    total_credits_distributed: int = 0
    unique_users: int = 0
    unique_virtual_labs: int = 0


class PromotionCodeUsageStats(BaseModel):
    """Detailed usage statistics with recent redemptions."""

    promotion_code: str
    statistics: PromotionCodeStatistics
    recent_redemptions: List[PromotionCodeUsageOut] = Field(default_factory=list)


class PromotionAnalytics(BaseModel):
    """System-wide promotion analytics."""

    total_promotions: int = 0
    active_promotions: int = 0
    expired_promotions: int = 0
    total_redemptions: int = 0
    total_credits_distributed: int = 0


class RedemptionHistoryItem(BaseModel):
    """User's redemption history item."""

    id: UUID
    promotion_code: str
    credits_granted: int
    virtual_lab_id: UUID
    virtual_lab_name: str
    status: PromotionCodeUsageStatus
    redeemed_at: datetime

    model_config = {"from_attributes": True}


class PromotionCodeListFilters(BaseModel):
    """Filters for listing promotion codes."""

    active: Optional[bool] = None
    search: Optional[str] = Field(
        default=None, max_length=100, description="Search by code or description"
    )
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class UsageHistoryFilters(BaseModel):
    """Filters for user redemption history."""

    virtual_lab_id: Optional[UUID] = None
    status: Optional[PromotionCodeUsageStatus] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PromotionUsageFilters(BaseModel):
    """Filters for promotion usage statistics."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[PromotionCodeUsageStatus] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaginationOut(BaseModel):
    """Pagination metadata for list responses."""

    total: int
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def create(cls, total: int, limit: int, offset: int) -> "PaginationOut":
        """Create pagination metadata."""
        return cls(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )
