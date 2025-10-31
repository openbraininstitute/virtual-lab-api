import asyncio
from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from jwt import ExpiredSignatureError, PyJWTError
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError, UserMatch
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.email.email_utils import (
    InviteOrigin,
    get_invite_details_from_token,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
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
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def invitation_handler(
    session: AsyncSession,
    *,
    invite_token: str,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    imr = InviteMutationRepository(session)
    pqr = ProjectQueryRepository(session)
    iqr = InviteQueryRepository(session)
    umr = UserMutationRepository()
    gqr = GroupQueryRepository()
    uqr = UserQueryRepository()

    try:
        decoded_token = get_invite_details_from_token(
            invite_token=invite_token,
        )
        user_id = get_user_id_from_auth(auth)
        invite_id = decoded_token.get("invite_id")
        origin = decoded_token.get("origin")
        virtual_lab_id = None
        project_id = None

        user = await uqr.a_retrieve_user_from_kc(
            user_id=str(user_id),
        )
        assert user is not None

        if origin == InviteOrigin.LAB.value:
            vlab_invite = await iqr.get_vlab_invite_by_id(invite_id=UUID(invite_id))
            if vlab_invite.accepted:
                return VliResponse.new(
                    message=f"Invite for vlab: {vlab_invite.virtual_lab_id} already accepted",
                    data={
                        "origin": origin,
                        "invite_id": invite_id,
                        "virtual_lab_id": vlab_invite.virtual_lab_id,
                        "status": "already_accepted",
                    },
                )

            virtual_lab = await get_undeleted_virtual_lab(
                db=session,
                lab_id=UUID(str(vlab_invite.virtual_lab_id)),
            )

            if virtual_lab.owner_id == user_id:
                raise UserMatch

            attach_group_id, detach_group_id = (
                (virtual_lab.admin_group_id, virtual_lab.member_group_id)
                if vlab_invite.role == UserRoleEnum.admin.value
                else (virtual_lab.member_group_id, virtual_lab.admin_group_id)
            )

            await asyncio.gather(
                umr.a_detach_user_from_group(
                    user_id=UUID(user.id),
                    group_id=str(detach_group_id),
                ),
                umr.a_attach_user_to_group(
                    user_id=UUID(user.id),
                    group_id=str(attach_group_id),
                ),
            )

            # if the user invited as admin
            # then add him to all virtual lab's projects admin group
            if vlab_invite.role == UserRoleEnum.admin.value:
                result = await pqr.retrieve_virtual_lab_projects(
                    virtual_lab_id=virtual_lab.id,
                )
                batch_attach_users = [
                    umr.a_attach_user_to_group(
                        user_id=user_id, group_id=proj.admin_group_id
                    )
                    for proj in result
                ]
                await asyncio.gather(*batch_attach_users)

            await imr.update_lab_invite(
                invite_id=UUID(str(vlab_invite.id)),
                user_id=user_id,
                accepted=True,
            )
            await session.refresh(virtual_lab)

            virtual_lab_id = virtual_lab.id

        elif origin == InviteOrigin.PROJECT.value:
            project_invite = await iqr.get_project_invite_by_id(
                invite_id=UUID(invite_id)
            )
            project, virtual_lab = await pqr.retrieve_one_project_by_id(
                project_id=project_invite.project_id,
            )
            if project_invite.accepted:
                return VliResponse.new(
                    message=f"Invite for project: {project_invite.project} already accepted",
                    data={
                        "origin": origin,
                        "invite_id": invite_id,
                        "virtual_lab_id": str(project.virtual_lab_id),
                        "project_id": str(project.id),
                        "status": "already_accepted",
                    },
                )

            if project.owner_id == user_id or virtual_lab.owner_id == user_id:
                raise UserMatch

            virtual_lab_member_group_id = virtual_lab.member_group_id
            virtual_lab_admin_group_id = virtual_lab.admin_group_id

            attach_group_id, detach_group_id = (
                (project.admin_group_id, project.member_group_id)
                if project_invite.role == UserRoleEnum.admin.value
                else (project.member_group_id, project.admin_group_id)
            )

            # detach the user from other groups
            # and attach it to the new group based on the role
            _, _, virtual_lab_admin_users = await asyncio.gather(
                umr.a_detach_user_from_group(
                    user_id=UUID(user.id),
                    group_id=detach_group_id,
                ),
                umr.a_attach_user_to_group(
                    user_id=UUID(user.id),
                    group_id=attach_group_id,
                ),
                # retrieve the virtual lab admin group users
                gqr.a_retrieve_group_user_ids(
                    group_id=virtual_lab_admin_group_id,
                ),
            )
            # if the user is not an admin of virtual lab
            # added it to the virtual lab member group
            if user.id not in virtual_lab_admin_users:
                await umr.a_attach_user_to_group(
                    user_id=UUID(user.id),
                    group_id=virtual_lab_member_group_id,
                )
            # update invite to be accepted
            await imr.update_project_invite(
                invite_id=project_invite.id,
                properties={"accepted": True, "user_id": user_id},
            )

            await session.refresh(project)
            await session.refresh(virtual_lab)

            virtual_lab_id = virtual_lab.id
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
    except UserMatch as ex:
        logger.error(f"Error during processing the invite: ({ex})")
        raise VliError(
            error_code=VliErrorCode.DATA_CONFLICT,
            http_status_code=status.BAD_REQUEST,
            message="Inviter user is the same as invitee user",
            details="Invitation is forbidden",
        )
    except ExpiredSignatureError as ex:
        logger.error(f"Error during processing the invite: ({ex})")
        raise VliError(
            error_code=VliErrorCode.TOKEN_EXPIRED,
            http_status_code=status.BAD_REQUEST,
            message="Invite Token is not valid",
            details="Invitation is expired",
        )
    except PyJWTError as ex:
        logger.error(f"Error during processing the invite: ({ex})")
        raise VliError(
            error_code=VliErrorCode.INVALID_PARAMETER,
            http_status_code=status.BAD_REQUEST,
            message="Invite Token is not valid",
            details="Invitation token is malformed",
        )
    except SQLAlchemyError as ex:
        logger.error(
            f"Invite {decoded_token.get('invite_id', None)} not found for origin {decoded_token.get('origin')}"
        )
        logger.exception("————> ex", ex)
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=status.NOT_FOUND,
            message="No invite was found for this link",
            details="The invite link is either malformed or the invite is deleted",
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
        logger.exception(f"Error during processing the invitation: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Processing invitation failed",
            details=str(ex),
        )
