"""
Use case for redeeming a promotion code.
Handles the complete redemption flow including validation, accounting integration, and recording.
"""

import logging
from http import HTTPStatus as status
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization.verify_vlab_write import (
    authorize_user_for_vlab_write,
)
from virtual_labs.core.exceptions.accounting_error import AccountingError
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.promotion_error import (
    PromotionAccountingError,
    PromotionNotFoundError,
)
from virtual_labs.domain.promotion import RedemptionResult
from virtual_labs.external.accounting.top_up_virtual_lab_budget import (
    top_up_virtual_lab_budget,
)
from virtual_labs.infrastructure.db.models import PromotionCodeUsageStatus
from virtual_labs.repositories import promotion_repo, promotion_usage_repo
from virtual_labs.services.promotion_validator import PromotionValidator

logger = logging.getLogger(__name__)


async def redeem_promotion_code(
    session: AsyncSession,
    code: str,
    user_id: UUID,
    virtual_lab_id: UUID,
) -> RedemptionResult:
    """
    Redeem a promotion code for a virtual lab.

    This function performs the following steps:
    1. Validates the promotion code and user eligibility
    2. Creates a pending redemption record
    3. Calls the accounting system to credit the virtual lab
    4. Updates the redemption status to completed
    5. Increments the promotion usage counter

    Args:
        db: Database session
        code: Promotion code to redeem
        user_id: User redeeming the code
        virtual_lab_id: Virtual lab to receive credits

    Returns:
        RedemptionResult with details of the redemption

    Raises:
        PromotionNotFoundError: If code doesn't exist
        PromotionExpiredError: If code has expired
        PromotionNotActiveError: If code is not active
        PromotionAlreadyUsedError: If user already used the code
        PromotionUsageLimitReachedError: If usage limit reached
        PromotionAccountingError: If accounting system fails
        PromotionRedemptionError: For other redemption failures
    """

    try:
        await authorize_user_for_vlab_write(
            str(user_id),
            virtual_lab_id,
            session,
        )
    except Exception:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=status.FORBIDDEN,
            message="The supplied authentication is not authorized for this action",
        )

    validator = PromotionValidator(session)

    try:
        promotion = await promotion_repo.get_by_code(session, code, for_update=True)

        if promotion is None:
            await promotion_usage_repo.record_attempt(
                db=session,
                code_attempted=code,
                user_id=user_id,
                virtual_lab_id=virtual_lab_id,
                success=False,
                failure_reason=PromotionNotFoundError.__name__,
            )
            await session.commit()
            raise PromotionNotFoundError(
                code=code,
            )
        await validator.validate_all(
            code=promotion.code,
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
        )

        usage = await promotion_usage_repo.create_usage(
            db=session,
            promotion_code_id=promotion.id,
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            credits_granted=int(promotion.credits_amount),
            status=PromotionCodeUsageStatus.PENDING,
        )

        try:
            accounting_response = await top_up_virtual_lab_budget(
                virtual_lab_id=virtual_lab_id,
                amount=float(promotion.credits_amount),
            )

            transaction_id = (
                str(accounting_response.id)
                if hasattr(accounting_response, "id")
                else None
            )

        except Exception as e:
            logger.error(
                f"Accounting system failed for promotion '{code}': {str(e)}",
                exc_info=True,
            )

            await promotion_usage_repo.update_status(
                db=session,
                usage_id=usage.id,
                status=PromotionCodeUsageStatus.FAILED,
                error_message=str(e),
            )

            await promotion_usage_repo.record_attempt(
                db=session,
                code_attempted=code,
                user_id=user_id,
                virtual_lab_id=virtual_lab_id,
                success=False,
                failure_reason="AccountingSystemError",
            )

            await session.commit()

            raise PromotionAccountingError(
                message=f"Accounting system failed to top up virtual lab '{code}': {str(e)}",
                code=code,
                virtual_lab_id=virtual_lab_id,
                details=e.type.value
                if isinstance(e, AccountingError) and e.type
                else None,
            ) from e

        await promotion_usage_repo.update_status(
            db=session,
            usage_id=usage.id,
            status=PromotionCodeUsageStatus.COMPLETED,
            accounting_transaction_id=transaction_id,
        )

        await promotion_repo.increment_usage_counter(session, promotion.id)
        await promotion_usage_repo.record_attempt(
            db=session,
            code_attempted=code,
            user_id=user_id,
            virtual_lab_id=virtual_lab_id,
            success=True,
        )

        await session.commit()
        await session.refresh(usage)
        await session.refresh(promotion)

        return RedemptionResult(
            redemption_id=usage.id,
            promotion_code=promotion.code,
            credits_granted=int(promotion.credits_amount),
            virtual_lab_id=virtual_lab_id,
            status=PromotionCodeUsageStatus.COMPLETED,
            redeemed_at=usage.redeemed_at,
            accounting_transaction_id=transaction_id,
        )

    except PromotionAccountingError:
        raise

    except Exception as e:
        await session.rollback()
        try:
            await promotion_usage_repo.record_attempt(
                db=session,
                code_attempted=code,
                user_id=user_id,
                virtual_lab_id=virtual_lab_id,
                success=False,
                failure_reason=type(e).__name__,
            )
            await session.commit()
        except Exception:
            pass

        raise
