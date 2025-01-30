from http import HTTPStatus as status
from uuid import UUID

from fastapi import Response
from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
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
        virtual_lab_id, project_id = None, None
        if origin.value == InviteOrigin.LAB.value:
            vlab_invite = await invite_query_repo.get_vlab_invite_by_id(
                invite_id=UUID(str(invite_id))
            )
            if vlab_invite.accepted:
                return VliResponse.new(
                    message=f"Invite for vlab: {vlab_invite.virtual_lab_id} already accepted",
                    data={
                        "origin": origin,
                        "invite_id": invite_id,
                        "virtual_lab_id": vlab_invite.virtual_lab_id,
                        "project_id": project_id,
                        "status": "already_accepted",
                    },
                )

            vlab = await get_undeleted_virtual_lab(
                db=session,
                lab_id=UUID(str(vlab_invite.virtual_lab_id)),
            )
            user = user_query_repo.retrieve_user_by_email(
                email=str(vlab_invite.user_email),
            )
            assert user is not None
            group_id = (
                vlab.admin_group_id
                if vlab_invite.role == UserRoleEnum.admin.value
                else vlab.member_group_id
            )
            user_mut_repo.attach_user_to_group(
                user_id=UUID(user.id),
                group_id=str(group_id),
            )

            await invite_mut_repo.update_lab_invite(
                invite_id=UUID(str(vlab_invite.id)),
                accepted=True,
            )
            await session.refresh(vlab)
            virtual_lab_id = vlab.id

        elif origin.value == InviteOrigin.PROJECT.value:
            project_invite = await invite_query_repo.get_project_invite_by_id(
                invite_id=UUID(str(invite_id))
            )

            project, vlab = await project_query_repo.retrieve_one_project_by_id(
                project_id=UUID(str(project_invite.project_id))
            )

            if project_invite.accepted:
                return VliResponse.new(
                    message="Invite for project: {}/{} already accepted".format(
                        project_invite.project.virtual_lab_id,
                        project_invite.project_id,
                    ),
                    data={
                        "origin": origin,
                        "invite_id": invite_id,
                        "virtual_lab_id": project.virtual_lab_id,
                        "project_id": project.id,
                        "status": "already_accepted",
                    },
                )
            user = user_query_repo.retrieve_user_by_email(
                email=str(project_invite.user_email)
            )
            assert user is not None

            group_id = (
                project.admin_group_id
                if project_invite.role == UserRoleEnum.admin.value
                else project.member_group_id
            )
            user_mut_repo.attach_user_to_group(
                user_id=UUID(user.id),
                group_id=str(group_id),
            )
            # user should be added to vlab members too
            # if not the user can not fetch the vlab details
            user_mut_repo.attach_user_to_group(
                user_id=UUID(user.id),
                group_id=str(vlab.member_group_id),
            )

            await invite_mut_repo.update_project_invite(
                invite_id=UUID(str(project_invite.id)),
                properties={"accepted": True, "updated_at": func.now()},
            )
            await session.refresh(project)

            virtual_lab_id = project.virtual_lab_id
            project_id = project.id
        else:
            raise ValueError(f"Origin {origin} is not allowed.")

        return VliResponse.new(
            message=f"Invite for {origin} accepted successfully",
            data={
                "origin": origin,
                "invite_id": invite_id,
                "virtual_lab_id": virtual_lab_id,
                "project_id": project_id,
                "status": "accepted",
            },
        )
    except (ValueError, AssertionError) as ex:
        logger.error(f"Could not retrieve users from keycloak: ({ex})")
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=status.BAD_REQUEST,
            message=str(ex),
        )
    except IdentityError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            message="Could not attach user to group",
        )
    except Exception as ex:
        print(ex)
        logger.error(f"Error during processing the invitation: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Processing invitation failed",
            details=str(ex),
        )
