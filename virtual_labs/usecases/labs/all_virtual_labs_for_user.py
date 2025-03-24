import asyncio
from http import HTTPStatus
from typing import Sequence, Tuple
from uuid import UUID

from keycloak import KeycloakGetError  # type: ignore
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.common import VirtualLabResponse
from virtual_labs.domain.labs import VirtualLabDetails, VirtualLabWithInviteDetails
from virtual_labs.infrastructure.db.models import VirtualLab
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
) -> VirtualLabResponse[VirtualLabDetails | None]:
    invite_repo = InviteQueryRepository(session=session)
    pqr = ProjectQueryRepository(session=session)
    gqr = GroupQueryRepository()

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
        user_groups = await gqr.a_retrieve_user_groups(user_id=str(user_id))
        group_ids = [g.id for g in user_groups if "vlab" in g.name]
        vlabs_adhered = await repository.get_virtual_labs_in_list(
            db=session, group_ids=group_ids
        )
        filtered_vlabs: Sequence[VirtualLab] = list(
            filter(
                lambda lab: lab.id != virtual_lab.id if virtual_lab else True,
                vlabs_adhered,
            )
        )

        membership_labs_with_counts: list[VirtualLabDetails | None] = []
        for _lab in filtered_vlabs:
            admin_users, member_users, total_projects = await asyncio.gather(
                gqr.a_retrieve_group_users(group_id=str(_lab.admin_group_id)),
                gqr.a_retrieve_group_users(group_id=str(_lab.member_group_id)),
                pqr.retrieve_projects_per_lab_count(virtual_lab_id=UUID(str(_lab.id))),
            )
            total_members = len(admin_users) + len(member_users)

            lab_with_counts = VirtualLabDetails(
                **{
                    column.name: getattr(_lab, column.name)
                    for column in _lab.__table__.columns
                },
                members_count=total_members,
                projects_count=total_projects,
            )
            membership_labs_with_counts.append(lab_with_counts)

        if not virtual_lab:
            return VirtualLabResponse(
                pending_labs=pending_labs,
                membership_labs=membership_labs_with_counts,
                virtual_lab=None,
            )

        admin_users, member_users, total_projects = await asyncio.gather(
            gqr.a_retrieve_group_users(group_id=str(virtual_lab.admin_group_id)),
            gqr.a_retrieve_group_users(group_id=str(virtual_lab.member_group_id)),
            pqr.retrieve_projects_per_lab_count(
                virtual_lab_id=UUID(str(virtual_lab.id))
            ),
        )

        total_members = len(admin_users) + len(member_users)

        return VirtualLabResponse(
            pending_labs=pending_labs,
            membership_labs=membership_labs_with_counts,
            virtual_lab=VirtualLabDetails(
                **{
                    column.name: getattr(virtual_lab, column.name)
                    for column in virtual_lab.__table__.columns
                },
                members_count=total_members,
                projects_count=total_projects,
            ),
        )
    except KeycloakGetError as ex:
        logger.exception(ex)
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Error retrieving groups from keycloak",
        )
    except Exception as ex:
        logger.exception(ex)
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Error retrieving virtual labs",
        )
