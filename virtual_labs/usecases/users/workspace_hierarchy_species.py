"""
Workspace Hierarchy Species Preference Usecase

Handles CRUD operations for user's brain region/hierarchy preferences.
These preferences persist the user's selected hierarchy, species taxonomy,
and brain region context for workspace navigation.
"""

from http import HTTPStatus
from typing import Tuple
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from starlette.responses import Response

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.user import (
    WorkspaceHierarchySpeciesPreference,
    WorkspaceHierarchySpeciesPreferenceDict,
    WorkspaceHierarchySpeciesPreferenceResponse,
)
from virtual_labs.infrastructure.db.models import UserPreference
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_workspace_hierarchy_species_preference(
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    """
    Retrieve the user's workspace hierarchy species preference.

    Args:
        auth: Authentication tuple containing user info and token
        session: Database session

    Returns:
        Response: JSON response with preference data or null if not set
    """
    user_id = get_user_id_from_auth(auth)

    try:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.execute(stmt)
        preference = result.scalar_one_or_none()

        preference_data = None
        updated_at = None

        if preference and preference.workspace_hierarchy_species:
            pref_dict: WorkspaceHierarchySpeciesPreferenceDict = (
                preference.workspace_hierarchy_species
            )
            brain_region_id_str = pref_dict.get("brain_region_id")
            preference_data = WorkspaceHierarchySpeciesPreference(
                hierarchy_id=UUID(pref_dict["hierarchy_id"]),
                species_name=pref_dict["species_name"],
                brain_region_id=UUID(brain_region_id_str)
                if brain_region_id_str
                else None,
                brain_region_name=pref_dict.get("brain_region_name"),
            )
            updated_at = preference.updated_at

        response_data = WorkspaceHierarchySpeciesPreferenceResponse(
            user_id=user_id,
            preference=preference_data,
            updated_at=updated_at,
        )

        return VliResponse.new(
            message="Workspace hierarchy species preference retrieved",
            data=response_data.model_dump(mode="json"),
        )

    except Exception as e:
        logger.exception(
            f"Error retrieving workspace hierarchy species preference: {e}"
        )
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to retrieve workspace hierarchy species preference",
        ) from e


async def update_workspace_hierarchy_species_preference(
    payload: WorkspaceHierarchySpeciesPreference,
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    """
    Update or create the user's workspace hierarchy species preference.

    This is an upsert operation - creates the preference if it doesn't exist,
    or updates it if it does.

    Args:
        payload: The preference data to persist
        auth: Authentication tuple containing user info and token
        session: Database session

    Returns:
        Response: JSON response with updated preference data
    """
    user_id = get_user_id_from_auth(auth)

    try:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.execute(stmt)
        preference = result.scalar_one_or_none()

        preference_dict: WorkspaceHierarchySpeciesPreferenceDict = {
            "hierarchy_id": str(payload.hierarchy_id),
            "species_name": payload.species_name,
            "brain_region_id": str(payload.brain_region_id)
            if payload.brain_region_id
            else None,
            "brain_region_name": payload.brain_region_name,
        }

        if not preference:
            preference = UserPreference(
                user_id=user_id,
                workspace_hierarchy_species=preference_dict,
            )
            session.add(preference)
        else:
            preference.workspace_hierarchy_species = preference_dict
            flag_modified(preference, "workspace_hierarchy_species")

        await session.commit()
        await session.refresh(preference)

        response_data = WorkspaceHierarchySpeciesPreferenceResponse(
            user_id=user_id,
            preference=payload,
            updated_at=preference.updated_at,
        )

        return VliResponse.new(
            message="Workspace hierarchy species preference updated",
            data=response_data.model_dump(mode="json"),
        )

    except Exception as e:
        logger.exception(f"Error updating workspace hierarchy species preference: {e}")
        await session.rollback()
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to update workspace hierarchy species preference",
        ) from e
