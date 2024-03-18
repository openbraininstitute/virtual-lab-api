from pydantic import UUID4, EmailStr
from sqlalchemy import func, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import and_

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.db.models import VirtualLabInvite


class InviteQueryRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

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

    def update_invite(self, invite_id: UUID4, accepted: bool) -> None:
        statement = (
            update(VirtualLabInvite)
            .where(VirtualLabInvite.id == invite_id)
            .values(accepted=accepted, updated_at=func.now())
        )
        self.session.execute(statement=statement)
        self.session.commit()
        return
