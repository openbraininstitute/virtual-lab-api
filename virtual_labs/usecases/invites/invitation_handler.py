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
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
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
    invite_mut_repo = InviteMutationRepository(session)
    invite_query_repo = InviteQueryRepository(session)
    user_mut_repo = UserMutationRepository()
    user_query_repo = UserQueryRepository()

    try:
        decoded_token = get_invite_details_from_token(
            invite_token=invite_token,
        )
        user_id = get_user_id_from_auth(auth)
        invite_id = decoded_token.get("invite_id")
        origin = decoded_token.get("origin")
        virtual_lab_id = None

        if origin == InviteOrigin.LAB.value:
            # check if the invite already accepted
            vlab_invite = await invite_query_repo.get_vlab_invite_by_id(
                invite_id=UUID(invite_id)
            )
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

            # check if the user invite himself
            vlab = await get_undeleted_virtual_lab(
                db=session,
                lab_id=UUID(str(vlab_invite.virtual_lab_id)),
            )

            if UUID(str(vlab.owner_id)) == user_id:
                raise UserMatch

            user = user_query_repo.retrieve_user_from_kc(user_id=str(user_id))
            assert user is not None

            # get the group of the virtual lab based on the invite role
            group_id = (
                vlab.admin_group_id
                if vlab_invite.role == UserRoleEnum.admin.value
                else vlab.member_group_id
            )
            remaining_group_id = (
                vlab.member_group_id
                if group_id == vlab.admin_group_id
                else vlab.admin_group_id
            )
            # detach the user from other groups
            # and attach it to the new group based on the role
            await asyncio.gather(
                user_mut_repo.a_detach_user_from_group(
                    user_id=UUID(user.id),
                    group_id=str(remaining_group_id),
                ),
                user_mut_repo.a_attach_user_to_group(
                    user_id=UUID(user.id),
                    group_id=str(group_id),
                ),
            )
            # update invite to be accepted
            await invite_mut_repo.update_lab_invite(
                invite_id=UUID(str(vlab_invite.id)),
                user_id=user_id,
                accepted=True,
            )
            await session.refresh(vlab)
            virtual_lab_id = vlab.id

        else:
            raise ValueError(f"Origin {origin} is not allowed.")

        return VliResponse.new(
            message=f"Invite for {origin} accepted successfully",
            data={
                "origin": origin,
                "invite_id": invite_id,
                "virtual_lab_id": virtual_lab_id,
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
    except SQLAlchemyError:
        logger.error(
            f"Invite {decoded_token.get('invite_id', None)} not found for origin {decoded_token.get('origin')}"
        )
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
        logger.error(f"Error during processing the invitation: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Processing invitation failed",
            details=str(ex),
        )
