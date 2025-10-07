from typing import Optional

from pydantic import UUID4
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.user import Workspace
from virtual_labs.infrastructure.db.models import UserPreference


class UserPreferenceQueryRepository:
    """Repository for querying user preferences"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_preference(self, user_id: UUID4) -> Optional[UserPreference]:
        """Get user preference by user ID"""
        query = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_recent_workspace(self, user_id: UUID4) -> Optional[Workspace]:
        """Get user's recent workspace"""
        preference = await self.get_user_preference(user_id)
        if preference and preference.virtual_lab_id and preference.project_id:
            return Workspace(
                virtual_lab_id=preference.virtual_lab_id,
                project_id=preference.project_id,
            )
        return None


class UserPreferenceMutationRepository:
    """Repository for mutating user preferences"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_user_preference(
        self,
        user_id: UUID4,
        virtual_lab_id: Optional[UUID4] = None,
        project_id: Optional[UUID4] = None,
    ) -> UserPreference:
        """Create or update user preference"""
        # Check if preference already exists
        existing = await self.session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        preference = existing.scalar_one_or_none()

        if preference:
            # Update existing preference
            if virtual_lab_id is not None:
                preference.virtual_lab_id = virtual_lab_id
            if project_id is not None:
                preference.project_id = project_id
            await self.session.commit()
            await self.session.refresh(preference)
            return preference
        else:
            # Create new preference
            new_preference = UserPreference(
                user_id=user_id, virtual_lab_id=virtual_lab_id, project_id=project_id
            )
            self.session.add(new_preference)
            await self.session.commit()
            await self.session.refresh(new_preference)
            return new_preference

    async def set_recent_workspace(
        self, user_id: UUID4, workspace: Workspace
    ) -> UserPreference:
        """Set user's recent workspace"""
        return await self.upsert_user_preference(
            user_id=user_id,
            virtual_lab_id=workspace.virtual_lab_id,
            project_id=workspace.project_id,
        )

    async def clear_recent_workspace(self, user_id: UUID4) -> None:
        """Clear user's recent workspace"""
        await self.session.execute(
            update(UserPreference)
            .where(UserPreference.user_id == user_id)
            .values(virtual_lab_id=None, project_id=None)
        )
        await self.session.flush()

    async def delete_user_preference(self, user_id: UUID4) -> None:
        """Delete user preference completely"""
        await self.session.execute(
            delete(UserPreference).where(UserPreference.user_id == user_id)
        )
        await self.session.flush()
