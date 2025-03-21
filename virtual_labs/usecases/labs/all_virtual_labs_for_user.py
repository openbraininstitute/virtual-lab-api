import asyncio
from http import HTTPStatus
from typing import Tuple
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.domain.common import LabListWithPending
from virtual_labs.domain.labs import VirtualLabDetails, VirtualLabWithInviteDetails
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.invite_repo import InviteQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.auth import (
    get_user_email_from_auth,
    get_user_id_from_auth,
)


async def list_user_virtual_labs(
    session: AsyncSession,
    auth: Tuple[AuthUser, str],
) -> LabListWithPending[VirtualLabDetails | None]:
    invite_repo = InviteQueryRepository(session=session)
    gqr = GroupQueryRepository()
    pqr = ProjectQueryRepository(session=session)

    try:
        user_id = get_user_id_from_auth(auth)
        user_email = get_user_email_from_auth(auth)

        virtual_lab = await repository.get_user_virtual_lab(
            db=session, owner_id=user_id
        )
        pending_vlab_invites = await invite_repo.get_user_invited_virtual_labs_by_email(
            email=user_email
        )
        pending_labs = [
            VirtualLabWithInviteDetails(
                **VirtualLabDetails.model_validate(lab).model_dump(),
                invite_id=invite_id,
            )
            for lab, invite_id in pending_vlab_invites
        ]
        if not virtual_lab:
            return LabListWithPending(
                pending_labs=pending_labs,
                virtual_lab=None,
                members_count=0,
                projects_count=0,
            )

        admin_users, member_users, user_groups, total_projects = await asyncio.gather(
            gqr.a_retrieve_group_users(group_id=str(virtual_lab.admin_group_id)),
            gqr.a_retrieve_group_users(group_id=str(virtual_lab.member_group_id)),
            gqr.a_retrieve_user_groups(user_id=user_id),
            pqr.retrieve_projects_per_lab_count(
                virtual_lab_id=UUID(str(virtual_lab.id))
            ),
        )
        group_ids = [g.id for g in user_groups if "vlab" in g.name]
        vlabs_adhered = await repository.get_virtual_labs_in_list(
            db=session, group_ids=group_ids
        )
        filtered_vlabs = list(
            filter(lambda lab: lab.id != virtual_lab.id, vlabs_adhered)
        )
        adhere_labs = list(
            map(
                lambda lab: VirtualLabDetails.model_validate(lab).model_dump(),
                filtered_vlabs,
            )
        )
        total_members = len(admin_users) + len(member_users)

        return LabListWithPending(
            pending_labs=pending_labs,
            membership_labs=adhere_labs,
            virtual_lab=VirtualLabDetails.model_validate(virtual_lab),
            members_count=total_members,
            projects_count=total_projects,
        )
    except IdentityError as ex:
        logger.exception(ex)
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=HTTPStatus.UNAUTHORIZED,
            message="User is not authenticated to retrieve virtual labs",
        )
    except Exception as ex:
        logger.exception(ex)
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Error retrieving virtual labs",
        )
