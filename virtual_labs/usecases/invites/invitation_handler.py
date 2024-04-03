from sqlalchemy.orm import Session

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.project import ProjectInviteOut
from virtual_labs.repositories.invite_repo import InviteMutationRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository


async def invitation_handler(
    session: Session,
    *,
    invite_token: str,
) -> VliAppResponse[ProjectInviteOut]:
    pr = ProjectQueryRepository(session)
    invite_repo = InviteMutationRepository(session)
    user_repo = UserQueryRepository()

    try:
        pass
    except Exception:
        pass
