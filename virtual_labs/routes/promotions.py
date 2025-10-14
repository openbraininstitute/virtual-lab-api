"""
Promotion code API routes.
Provides endpoints for redeeming codes, viewing history, and admin management.
"""

from http import HTTPStatus
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.exceptions.promotion_error import PromotionError
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.promotion import (
    PromotionAnalytics,
    PromotionCodeCreate,
    PromotionCodeDetail,
    PromotionCodeListFilters,
    PromotionCodeUpdate,
    PromotionCodeUsageStats,
    PromotionUsageFilters,
    RedeemPromotionCodeRequest,
    RedemptionResult,
    UsageHistoryFilters,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis.promotion_limiter import (
    rate_limit_promotion_redemption,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases.promotion import (
    get_user_redemption_history as get_history_usecase,
)
from virtual_labs.usecases.promotion import (
    redeem_promotion_code as redeem_usecase,
)
from virtual_labs.usecases.promotion.admin import (
    create_promotion_code as create_promo_usecase,
)
from virtual_labs.usecases.promotion.admin import (
    deactivate_promotion_code as deactivate_usecase,
)
from virtual_labs.usecases.promotion.admin import (
    get_promotion_details as get_details_usecase,
)
from virtual_labs.usecases.promotion.admin import (
    get_promotion_statistics as get_stats_usecase,
)
from virtual_labs.usecases.promotion.admin import (
    list_promotions as list_usecase,
)
from virtual_labs.usecases.promotion.admin import (
    update_promotion_code as update_usecase,
)

router = APIRouter(
    prefix="/promotions",
    tags=["Promotion Codes"],
)

admin_router = APIRouter(
    prefix="/admin/promotions",
    tags=["Promotion Codes (Admin)"],
)


# User-Facing Endpoints
@router.post(
    "/redeem",
    operation_id="redeem_promotion_code",
    summary="Redeem a promotion code for credits",
    description=(
        "Redeem a promotion code to receive credits for a virtual lab."
        "The code must be active, within its validity period, and you must"
        "not have exceeded the usage limit for this code."
        "Rate limited to 3 attempts per 30 minutes per user."
    ),
    response_model=VliAppResponse[RedemptionResult],
    status_code=HTTPStatus.OK,
)
@rate_limit_promotion_redemption(
    max_attempts=3,
    window_seconds=1800,
    prefix="promotion_code",
)
async def redeem_promotion_code(
    payload: RedeemPromotionCodeRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[RedemptionResult]:
    """
    Redeem a promotion code.

    This endpoint validates the code, credits the virtual lab, and records the redemption.
    Rate limited to 3 attempts per 30 minutes per user.
    """
    user_id = get_user_id_from_auth(auth)

    try:
        result = await redeem_usecase.redeem_promotion_code(
            session=session,
            code=payload.code,
            user_id=user_id,
            virtual_lab_id=payload.virtual_lab_id,
        )

        return VliAppResponse(
            message="Promotion code redeemed successfully",
            data=result,
        )

    except PromotionError as e:
        raise VliError(
            error_code=e.error_code,
            http_status_code=e.http_status_code,
            message=e.message,
            details=e.details,
            data=e.data,
        )


@router.get(
    "/usage",
    operation_id="get_user_redemption_history",
    summary="Get user's promotion code redemption history",
    description=(
        "Retrieve the authenticated user's history of promotion code redemptions "
        "with optional filtering by virtual lab and status."
    ),
    response_model=VliAppResponse[Dict[str, Any]],
    status_code=HTTPStatus.OK,
)
async def get_user_redemption_history(
    virtual_lab_id: UUID4 | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[Dict[str, Any]]:
    """
    Get user's redemption history with pagination.

    Query parameters:
    - virtual_lab_id: Filter by specific virtual lab (optional)
    - status: Filter by status (completed, pending, failed) (optional)
    - limit: Number of results per page (default: 20, max: 100)
    - offset: Number of results to skip (default: 0)
    """
    user_id = get_user_id_from_auth(auth)

    from virtual_labs.infrastructure.db.models import PromotionCodeUsageStatus

    status_enum = None
    if status:
        try:
            status_enum = PromotionCodeUsageStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Invalid status: {status}. Must be one of: pending, completed, failed, rolled_back",
            )

    filters = UsageHistoryFilters(
        virtual_lab_id=virtual_lab_id,
        status=status_enum,
        limit=min(limit, 100),
        offset=max(offset, 0),
    )

    usages, pagination = await get_history_usecase.get_user_redemption_history(
        session=session,
        user_id=user_id,
        filters=filters,
    )

    return VliAppResponse(
        message="Redemption history retrieved successfully",
        data={
            "redemptions": usages,
            "pagination": pagination,
        },
    )


# Admin Endpoints
@admin_router.post(
    "",
    operation_id="create_promotion_code",
    summary="Create a new promotion code (Admin only)",
    description="Create a new promotion code with specified credits and validity period.",
    response_model=VliAppResponse[PromotionCodeDetail],
    status_code=HTTPStatus.CREATED,
)
async def create_promotion_code(
    payload: PromotionCodeCreate,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[PromotionCodeDetail]:
    """
    Create a new promotion code (admin only).

    TODO: Add admin role verification
    """
    user_id = get_user_id_from_auth(auth)

    promotion = await create_promo_usecase.create_promotion_code(
        db=session,
        promotion_data=payload,
        admin_user_id=user_id,
    )

    return VliAppResponse(
        message="Promotion code created successfully",
        data=promotion,
    )


@admin_router.get(
    "",
    operation_id="list_promotion_codes",
    summary="List all promotion codes (Admin only)",
    description="List all promotion codes with filtering and pagination.",
    response_model=VliAppResponse[Dict[str, Any]],
    status_code=HTTPStatus.OK,
)
async def list_promotion_codes(
    active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[Dict[str, Any]]:
    """
    List all promotion codes (admin only).

    Query parameters:
    - active: Filter by active status (optional)
    - search: Search by code or description (optional)
    - limit: Number of results per page (default: 50, max: 100)
    - offset: Number of results to skip (default: 0)

    TODO: Add admin role verification
    """
    filters = PromotionCodeListFilters(
        active=active,
        search=search,
        limit=min(limit, 100),
        offset=max(offset, 0),
    )

    promotions, pagination = await list_usecase.list_promotions(
        db=session,
        filters=filters,
    )

    return VliAppResponse(
        message="Promotion codes retrieved successfully",
        data={
            "promotions": promotions,
            "pagination": pagination,
        },
    )


@admin_router.get(
    "/{promotion_id}",
    operation_id="get_promotion_code_details",
    summary="Get promotion code details (Admin only)",
    description="Get detailed information about a specific promotion code.",
    response_model=VliAppResponse[PromotionCodeDetail],
    status_code=HTTPStatus.OK,
)
async def get_promotion_code_details(
    promotion_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[PromotionCodeDetail]:
    """
    Get promotion code details (admin only).

    TODO: Add admin role verification
    """
    try:
        promotion = await get_details_usecase.get_promotion_details(
            db=session,
            promotion_id=promotion_id,
        )

        return VliAppResponse(
            message="Promotion code details retrieved successfully",
            data=promotion,
        )

    except PromotionError as e:
        raise HTTPException(
            status_code=e.http_status_code,
            detail={
                "error_code": e.error_code,
                "message": e.message,
                "details": e.details,
            },
        ) from e


@admin_router.put(
    "/{promotion_id}",
    operation_id="update_promotion_code",
    summary="Update a promotion code (Admin only)",
    description="Update selected fields of a promotion code. Cannot update code, credits amount, or usage counter.",
    response_model=VliAppResponse[PromotionCodeDetail],
    status_code=HTTPStatus.OK,
)
async def update_promotion_code(
    promotion_id: UUID4,
    payload: PromotionCodeUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[PromotionCodeDetail]:
    """
    Update a promotion code (admin only).

    TODO: Add admin role verification
    """
    try:
        promotion = await update_usecase.update_promotion_code(
            db=session,
            promotion_id=promotion_id,
            update_data=payload,
        )

        return VliAppResponse(
            message="Promotion code updated successfully",
            data=promotion,
        )

    except PromotionError as e:
        raise HTTPException(
            status_code=e.http_status_code,
            detail={
                "error_code": e.error_code,
                "message": e.message,
                "details": e.details,
            },
        ) from e


@admin_router.delete(
    "/{promotion_id}",
    operation_id="deactivate_promotion_code",
    summary="Deactivate a promotion code (Admin only)",
    description="Deactivate a promotion code (soft delete). The code can no longer be redeemed.",
    response_model=VliAppResponse[PromotionCodeDetail],
    status_code=HTTPStatus.OK,
)
async def deactivate_promotion_code(
    promotion_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[PromotionCodeDetail]:
    """
    Deactivate a promotion code (admin only).

    TODO: Add admin role verification
    """
    try:
        promotion = await deactivate_usecase.deactivate_promotion_code(
            db=session,
            promotion_id=promotion_id,
        )

        return VliAppResponse(
            message="Promotion code deactivated successfully",
            data=promotion,
        )

    except PromotionError as e:
        raise HTTPException(
            status_code=e.http_status_code,
            detail={
                "error_code": e.error_code,
                "message": e.message,
                "details": e.details,
            },
        ) from e


@admin_router.get(
    "/{promotion_id}/usage",
    operation_id="get_promotion_usage_statistics",
    summary="Get promotion code usage statistics (Admin only)",
    description="Get detailed usage statistics for a specific promotion code including recent redemptions.",
    response_model=VliAppResponse[PromotionCodeUsageStats],
    status_code=HTTPStatus.OK,
)
async def get_promotion_usage_statistics(
    promotion_id: UUID4,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[PromotionCodeUsageStats]:
    """
    Get usage statistics for a promotion code (admin only).

    Query parameters:
    - start_date: Filter from date (ISO format, optional)
    - end_date: Filter to date (ISO format, optional)
    - status: Filter by redemption status (optional)
    - limit: Number of recent redemptions to return (default: 20)
    - offset: Offset for pagination (default: 0)

    TODO: Add admin role verification
    """
    from datetime import datetime

    from virtual_labs.infrastructure.db.models import PromotionCodeUsageStatus

    # Parse dates
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Invalid start_date format: {start_date}",
            )

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Invalid end_date format: {end_date}",
            )

    # Parse status
    status_enum = None
    if status:
        try:
            status_enum = PromotionCodeUsageStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Invalid status: {status}",
            )

    filters = PromotionUsageFilters(
        start_date=start_dt,
        end_date=end_dt,
        status=status_enum,
        limit=min(limit, 100),
        offset=max(offset, 0),
    )

    try:
        stats = await get_stats_usecase.get_promotion_usage_statistics(
            db=session,
            promotion_id=promotion_id,
            filters=filters,
        )

        return VliAppResponse(
            message="Usage statistics retrieved successfully",
            data=stats,
        )

    except PromotionError as e:
        raise HTTPException(
            status_code=e.http_status_code,
            detail={
                "error_code": e.error_code,
                "message": e.message,
                "details": e.details,
            },
        ) from e


@admin_router.get(
    "/analytics/system",
    operation_id="get_system_promotion_analytics",
    summary="Get system-wide promotion analytics (Admin only)",
    description="Get system-wide statistics about all promotion codes and redemptions.",
    response_model=VliAppResponse[PromotionAnalytics],
    status_code=HTTPStatus.OK,
)
async def get_system_promotion_analytics(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[PromotionAnalytics]:
    """
    Get system-wide promotion analytics (admin only).

    TODO: Add admin role verification
    """
    analytics = await get_stats_usecase.get_system_analytics(db=session)

    return VliAppResponse(
        message="System analytics retrieved successfully",
        data=analytics,
    )
