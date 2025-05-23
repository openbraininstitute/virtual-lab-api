from typing import Any, Dict, List, Tuple
from uuid import UUID

from pydantic import UUID4, EmailStr
from sqlalchemy import and_, false, func, or_, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.db.models import (
    ProjectInvite,
    VirtualLab,
    VirtualLabInvite,
)


class InviteQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_pending_users_for_lab(self, lab_id: UUID4) -> list[VirtualLabInvite]:
        query = select(VirtualLabInvite).filter(
            VirtualLabInvite.virtual_lab_id == lab_id, ~VirtualLabInvite.accepted
        )
        invites = (await self.session.execute(query)).scalars().all()
        return list(invites)

    async def get_pending_users_for_project(
        self, project_id: UUID4
    ) -> list[ProjectInvite]:
        query = select(ProjectInvite).filter(
            and_(
                ProjectInvite.project_id == project_id,
                or_(ProjectInvite.accepted.is_(None), ~ProjectInvite.accepted),
            )
        )
        invites = (await self.session.execute(query)).scalars().all()
        return list(invites)

    async def get_vlab_invite_by_id(self, invite_id: UUID4) -> VirtualLabInvite:
        invite = await self.session.get(VirtualLabInvite, invite_id)
        if invite is None:
            raise NoResultFound
        return invite

    async def get_project_invite_by_id(self, invite_id: UUID4) -> ProjectInvite:
        invite = await self.session.get(ProjectInvite, invite_id)
        if invite is None:
            raise NoResultFound
        return invite

    async def get_lab_invite_by_params(
        self, lab_id: UUID4, email: str, role: UserRoleEnum
    ) -> VirtualLabInvite | None:
        statement = select(VirtualLabInvite).filter(
            VirtualLabInvite.virtual_lab_id == lab_id,
            VirtualLabInvite.user_email == email,
            VirtualLabInvite.role == role.value,
        )
        invite = (await self.session.execute(statement)).scalar()
        return invite

    async def get_project_invite_by_params(
        self,
        *,
        project_id: UUID4,
        email: EmailStr,
        role: UserRoleEnum,
    ) -> ProjectInvite | None:
        return (
            await self.session.execute(
                select(ProjectInvite).filter(
                    ProjectInvite.project_id == project_id,
                    ProjectInvite.user_email == email,
                    ProjectInvite.role == role.value,
                )
            )
        ).scalar()

    async def get_user_invited_virtual_labs_by_email(
        self,
        email: EmailStr,
    ) -> List[Tuple[VirtualLab, UUID]]:
        stmt = (
            select(VirtualLab, VirtualLabInvite.id.label("invite_id"))
            .join(VirtualLabInvite, VirtualLabInvite.virtual_lab_id == VirtualLab.id)
            .where(
                (VirtualLabInvite.user_email == email)
                & (VirtualLab.deleted == false())
                & (VirtualLabInvite.accepted == false())
            )
        )
        result = await self.session.execute(stmt)
        return [tuple(row) for row in result.all()]

    async def get_pending_invites_for_user(
        self,
        email: EmailStr,
    ) -> int:
        """Count all pending invites for a user by email"""
        # Count pending lab invites
        lab_stmt = (
            select(func.count())
            .select_from(VirtualLabInvite)
            .where(
                (VirtualLabInvite.user_email == email)
                & (VirtualLabInvite.accepted == false())
            )
        )
        result = await self.session.execute(lab_stmt)
        lab_count: int = result.scalar() or 0

        # Count pending project invites
        project_stmt = (
            select(func.count())
            .select_from(ProjectInvite)
            .where(
                (ProjectInvite.user_email == email)
                & (or_(ProjectInvite.accepted.is_(None), ~ProjectInvite.accepted))
            )
        )
        result = await self.session.execute(project_stmt)
        project_count: int = result.scalar() or 0

        return lab_count + project_count


class InviteMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_lab_invite(
        self,
        *,
        virtual_lab_id: UUID4,
        inviter_id: UUID4,
        invitee_role: UserRoleEnum,
        invitee_email: EmailStr,
    ) -> VirtualLabInvite:
        invite = VirtualLabInvite(
            inviter_id=inviter_id,
            virtual_lab_id=virtual_lab_id,
            role=invitee_role.value,
            user_email=invitee_email,
        )
        self.session.add(invite)
        await self.session.commit()
        await self.session.refresh(invite)
        return invite

    async def add_project_invite(
        self,
        *,
        project_id: UUID4,
        inviter_id: UUID4,
        invitee_role: UserRoleEnum,
        invitee_email: EmailStr,
        invitee_id: UUID4 | None,
    ) -> ProjectInvite:
        invite = ProjectInvite(
            inviter_id=inviter_id,
            user_id=invitee_id,
            project_id=project_id,
            role=invitee_role.value,
            user_email=invitee_email,
        )
        self.session.add(invite)
        await self.session.commit()
        await self.session.refresh(invite)
        return invite

    async def update_lab_invite(
        self,
        invite_id: UUID4,
        user_id: UUID | None = None,
        accepted: bool = False,
    ) -> None:
        statement = (
            update(VirtualLabInvite)
            .where(VirtualLabInvite.id == invite_id)
            .values(
                user_id=user_id,
                accepted=accepted,
                updated_at=func.now(),
            )
        )
        await self.session.execute(statement=statement)
        await self.session.commit()
        return

    async def update_project_invite(
        self, invite_id: UUID4, properties: Dict[str, Any]
    ) -> None:
        columns = ProjectInvite.__table__.columns.keys()
        values = {}

        for k, v in properties.items():
            if k in columns:
                values.update({k: v})

        statement = (
            update(ProjectInvite)
            .where(ProjectInvite.id == invite_id)
            .values(
                values,
            )
        )
        await self.session.execute(statement=statement)
        await self.session.commit()
        return

    async def delete_lab_invite(self, invite_id: UUID4) -> VirtualLabInvite:
        query_repo = InviteQueryRepository(session=self.session)
        invite = await query_repo.get_vlab_invite_by_id(invite_id)
        await self.session.delete(invite)
        await self.session.commit()
        return invite

    async def delete_project_invite(self, invite_id: UUID4) -> ProjectInvite:
        query_repo = InviteQueryRepository(session=self.session)
        invite = await query_repo.get_project_invite_by_id(invite_id)
        await self.session.delete(invite)
        await self.session.commit()
        return invite
