from http import HTTPStatus as status
from uuid import UUID

from fastapi import Response
from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.email.email_utils import InviteOrigin
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)


async def invitation_handler_test(
    session: AsyncSession,
    *,
    invite_id: UUID,
    origin: InviteOrigin,
) -> Response | VliError:
    project_query_repo = ProjectQueryRepository(session)
    invite_mut_repo = InviteMutationRepository(session)
    invite_query_repo = InviteQueryRepository(session)
    user_mut_repo = UserMutationRepository()
    user_query_repo = UserQueryRepository()

    try:
        if origin == InviteOrigin.PROJECT:
            project_invite = await invite_query_repo.get_project_invite_by_id(
                invite_id=invite_id
            )
            project, _ = await project_query_repo.retrieve_one_project_by_id(
                project_id=UUID(str(project_invite.project_id))
            )
            users = user_query_repo.retrieve_user_by_email_soft(
                email=str(project_invite.user_email)
            )
            if not (users and len(users)):
                user_id = user_mut_repo.create_test_user(
                    user_email=str(project_invite.user_email),
                )
            else:
                user_id = UUID(users[0].id)

            group_id = (
                project.admin_group_id
                if project_invite.role == UserRoleEnum.admin.value
                else project.member_group_id
            )
            user_mut_repo.attach_user_to_group(user_id=user_id, group_id=str(group_id))
            await invite_mut_repo.update_project_invite(
                invite_id=UUID(str(project_invite.id)),
                properties={"accepted": True, "updated_at": func.now()},
            )
        elif origin == InviteOrigin.LAB:
            vlab_invite = await invite_query_repo.get_vlab_invite_by_id(
                invite_id=invite_id
            )
            vlab = await get_undeleted_virtual_lab(
                db=session, lab_id=UUID(str(vlab_invite.virtual_lab_id))
            )
            users = user_query_repo.retrieve_user_by_email_soft(
                email=str(vlab_invite.user_email)
            )

            if not (users and len(users)):
                user_id = user_mut_repo.create_test_user(
                    user_email=str(vlab_invite.user_email),
                )
            else:
                user_id = UUID(users[0].id)
            group_id = (
                vlab.admin_group_id
                if vlab_invite.role == UserRoleEnum.admin.value
                else vlab.member_group_id
            )
            user_mut_repo.attach_user_to_group(user_id=user_id, group_id=str(group_id))

            await invite_mut_repo.update_lab_invite(
                invite_id=UUID(str(vlab_invite.id)),
                accepted=True,
            )
        else:
            raise Exception("unknown origin, please choose either Lab or Project")
    except Exception as ex:
        logger.error(f"Error during validating the invite ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Validating invite failed",
        )
    else:
        return VliResponse.new(
            message="Invite validated successfully",
            data=None,
        )
