from typing import Any, Dict

from pydantic import UUID4, EmailStr
from sqlalchemy import func, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import and_

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.db.models import ProjectInvite, VirtualLabInvite


class InviteQueryRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_project_invite_by_id(self, invite_id: UUID4) -> ProjectInvite:
        return (
            self.session.query(ProjectInvite)
            .filter(ProjectInvite.id == invite_id)
            .one()
        )

    def get_vlab_invite_by_id(self, invite_id: UUID4) -> VirtualLabInvite:
        return (
            self.session.query(VirtualLabInvite)
            .filter(VirtualLabInvite.id == invite_id)
            .one()
        )

    def get_project_invite_by_params(
        self,
        *,
        project_id: UUID4,
        email: EmailStr,
        role: UserRoleEnum,
    ) -> ProjectInvite | None:
        return (
            self.session.query(ProjectInvite)
            .filter(
                and_(
                    ProjectInvite.project_id == project_id,
                    ProjectInvite.user_email == email,
                    ProjectInvite.role == role.value,
                )
            )
            .first()
        )

    def get_pending_users_for_lab(self, lab_id: UUID4) -> list[VirtualLabInvite]:
        return (
            self.session.query(VirtualLabInvite)
            .filter(
                and_(
                    VirtualLabInvite.virtual_lab_id == lab_id,
                    ~VirtualLabInvite.accepted,
                )
            )
            .all()
        )


class InviteMutationRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_invite(self, invite_id: UUID4) -> VirtualLabInvite:
        return (
            self.session.query(VirtualLabInvite)
            .filter(VirtualLabInvite.id == invite_id)
            .one()
        )

    def add_lab_invite(
        self,
        *,
        virtual_lab_id: UUID4,
        inviter_id: UUID4,
        invitee_role: UserRoleEnum,
        invitee_email: EmailStr,
        invitee_id: UUID4 | None,
    ) -> VirtualLabInvite:
        invite = VirtualLabInvite(
            inviter_id=inviter_id,
            user_id=invitee_id,
            virtual_lab_id=virtual_lab_id,
            role=invitee_role.value,
            user_email=invitee_email,
        )
        self.session.add(invite)
        self.session.commit()
        self.session.refresh(invite)
        return invite

    def add_project_invite(
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
        self.session.commit()
        self.session.refresh(invite)
        return invite

    def update_project_invite(
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
        self.session.execute(statement=statement)
        self.session.commit()
        return

    def update_vlab_invite(self, invite_id: UUID4, accepted: bool) -> None:
        statement = (
            update(VirtualLabInvite)
            .where(VirtualLabInvite.id == invite_id)
            .values(accepted=accepted, updated_at=func.now())
        )
        self.session.execute(statement=statement)
        self.session.commit()
        return

    def delete_invite(self, invite_id: UUID4) -> VirtualLabInvite:
        invite = self.get_invite(invite_id)
        self.session.delete(invite)
        self.session.commit()
        return invite
