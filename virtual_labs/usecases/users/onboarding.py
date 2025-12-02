from http import HTTPStatus
from typing import Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from starlette.responses import Response

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.user import OnboardingStatusDict, OnboardingUpdateRequest
from virtual_labs.infrastructure.db.models import UserPreference
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_user_onboarding_status(
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    user_id = get_user_id_from_auth(auth)

    try:
        stmt = select(UserPreference.onboarding_progress).where(
            UserPreference.user_id == user_id
        )
        result = await session.execute(stmt)
        onboarding_progress = result.scalar_one_or_none()

        if not onboarding_progress:
            return VliResponse.new(
                message="Onboarding status retrieved",
                data=None,
            )

        return VliResponse.new(
            message="Onboarding status retrieved",
            data=onboarding_progress,
        )

    except Exception as e:
        logger.exception(e)
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while retrieving the user onboarding",
        ) from e


async def update_user_onboarding_status(
    feature: str,
    payload: OnboardingUpdateRequest,
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    user_id = get_user_id_from_auth(auth)

    try:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.execute(stmt)
        preference = result.scalar_one_or_none()

        if not preference:
            preference = UserPreference(user_id=user_id, onboarding_progress={})
            session.add(preference)

        current_progress: dict[str, OnboardingStatusDict] = dict(
            preference.onboarding_progress or {}
        )
        feature_progress: OnboardingStatusDict = current_progress.get(
            feature,
            {
                "completed": False,
                "completed_at": None,
                "current_step": None,
                "dismissed": False,
            },
        )

        if payload.completed is not None:
            feature_progress["completed"] = payload.completed
        if payload.current_step is not None:
            feature_progress["current_step"] = payload.current_step
        if payload.dismissed is not None:
            feature_progress["dismissed"] = payload.dismissed

        if payload.completed:
            from datetime import datetime, timezone

            feature_progress["completed_at"] = datetime.now(timezone.utc).isoformat()

        current_progress[feature] = feature_progress
        preference.onboarding_progress = current_progress
        flag_modified(preference, "onboarding_progress")

        await session.commit()

        return VliResponse.new(
            message="Onboarding status updated",
            data=current_progress,
        )
    except Exception as e:
        logger.exception(e)
        await session.rollback()
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while updating the user onboarding",
        ) from e


async def reset_user_onboarding_status(
    feature: str,
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    user_id = get_user_id_from_auth(auth)

    try:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.execute(stmt)
        preference = result.scalar_one_or_none()

        if not preference or not preference.onboarding_progress:
            return VliResponse.new(
                message="Reset onboarding",
                data=None,
            )

        current_progress = dict(preference.onboarding_progress)
        if feature in current_progress:
            del current_progress[feature]
            preference.onboarding_progress = current_progress
            flag_modified(preference, "onboarding_progress")
            await session.commit()

        return VliResponse.new(
            message="Onboarding status reset",
            data=current_progress,
        )
    except Exception as e:
        logger.exception(e)
        await session.rollback()
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while resetting the user onboarding feature",
        ) from e


async def reset_all_user_onboarding_status(
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    user_id = get_user_id_from_auth(auth)
    try:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.execute(stmt)
        preference = result.scalar_one_or_none()

        if not preference:
            return VliResponse.new(
                message="All onboarding status reset",
                data=None,
            )

        preference.onboarding_progress = {}
        flag_modified(preference, "onboarding_progress")
        await session.commit()

        return VliResponse.new(
            message="All onboarding status reset",
            data=None,
        )
    except Exception as e:
        logger.exception(e)
        await session.rollback()
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while resetting all user onboarding features",
        ) from e
