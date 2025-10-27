"""
Use case for retrieving user's promotion code redemption history.
"""

from http import HTTPStatus as status
from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization.verify_vlab_write import (
    authorize_user_for_vlab_write,
)
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.promotion import (
    PaginationOut,
    PromotionCodeUsageOut,
    UsageHistoryFilters,
)
from virtual_labs.repositories import promotion_usage_repo


async def get_user_redemption_history(
    session: AsyncSession,
    user_id: UUID,
    filters: UsageHistoryFilters,
) -> tuple[List[PromotionCodeUsageOut], PaginationOut]:
    """
    Get user's promotion code redemption history with pagination.

    Args:
        db: Database session
        user_id: User UUID
        filters: Filter and pagination parameters

    Returns:
        Tuple of (list of usage records, pagination metadata)
    """
    if filters.virtual_lab_id:
        try:
            await authorize_user_for_vlab_write(
                str(user_id),
                filters.virtual_lab_id,
                session,
            )
        except Exception:
            raise VliError(
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=status.FORBIDDEN,
                message="The supplied authentication is not authorized for this action",
            )

    usages, total = await promotion_usage_repo.get_user_usage_history(
        db=session,
        user_id=user_id,
        filters=filters,
    )

    # Convert to output schema
    usage_out_list: List[PromotionCodeUsageOut] = []
    for usage in usages:
        usage_out = PromotionCodeUsageOut(
            id=usage.id,
            promotion_code_id=usage.promotion_code_id,
            promotion_code=usage.promotion_code.code,
            user_id=usage.user_id,
            virtual_lab_id=usage.virtual_lab_id,
            virtual_lab_name=usage.virtual_lab.name if usage.virtual_lab else None,
            credits_granted=usage.credits_granted,
            status=usage.status,
            redeemed_at=usage.redeemed_at,
            accounting_transaction_id=usage.accounting_transaction_id,
            error_message=usage.error_message,
        )
        usage_out_list.append(usage_out)

    pagination = PaginationOut.create(
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )

    return usage_out_list, pagination
