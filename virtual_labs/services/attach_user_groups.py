import asyncio
from json import loads
from typing import Dict, List, Set, Tuple

from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4, EmailStr

from virtual_labs.core.exceptions.generic_exceptions import EntityNotFound
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.project import (
    AddUserProjectDetails,
    AddUserToProjectIn,
    AttachUserFailedOperation,
    EmailFailure,
)
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.email.add_member_to_project_email import (
    EmailDetails,
    send_add_member_to_project_email,
)
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository


async def get_project_and_vl_groups(
    project: Project,
    virtual_lab: VirtualLab,
    users: List[AddUserToProjectIn],
) -> Tuple[
    Dict[UUID4, AddUserToProjectIn],
    str,
    str,
    Set[str] | None,
    Set[str] | None,
    list[str] | None,
]:
    """
    Get project and virtual lab groups and validate users are part of the virtual lab

    Args:
        session: Database session
        project: Project object
        virtual_lab: Virtual lab object
        users: List of users to process

    Returns:
        Tuple containing:
        - unique_users_map: Dictionary mapping user ID to user data
        - project_admin_group_id: Project admin group ID
        - project_member_group_id: Project member group ID
        - existing_proj_admin_ids: Set of existing project admin user IDs
        - existing_proj_member_ids: Set of existing project member user IDs
    """
    gqr = GroupQueryRepository()
    unique_users_map: Dict[UUID4, AddUserToProjectIn] = {}

    for user_in in users:
        if user_in.id != project.owner_id:
            unique_users_map[user_in.id] = user_in

    if not unique_users_map:
        return unique_users_map, "", "", None, None, None

    # Get Virtual Lab group IDs
    vl_admin_group_id = str(virtual_lab.admin_group_id)
    vl_member_group_id = str(virtual_lab.member_group_id)

    # Get Virtual Lab users
    vl_admin_ids_list, vl_member_ids_list = await asyncio.gather(
        gqr.a_retrieve_group_user_ids(vl_admin_group_id),
        gqr.a_retrieve_group_user_ids(vl_member_group_id),
    )
    vl_all_member_ids: Set[str] = set(vl_admin_ids_list).union(set(vl_member_ids_list))

    # Check if ALL users are part of the Virtual Lab (admin or member)
    users_not_in_vl: List[UUID4] = []
    for user_to_check in unique_users_map.values():
        if str(user_to_check.id) not in vl_all_member_ids:
            users_not_in_vl.append(user_to_check.id)

    # If any user is not in the VL, raise an error immediately
    if users_not_in_vl:
        logger.error(
            f"Users not part of Virtual Lab {virtual_lab.id}: {[str(uid) for uid in users_not_in_vl]}"
        )
        raise EntityNotFound(
            "One or more users are not members of the parent Virtual Lab.",
            data={
                "users_not_in_virtual_lab": [str(uid) for uid in users_not_in_vl],
            },
        )

    # Get Project group IDs
    project_admin_group_id = str(project.admin_group_id)
    project_member_group_id = str(project.member_group_id)

    # Get Project users
    existing_proj_admin_ids_list, existing_proj_member_ids_list = await asyncio.gather(
        gqr.a_retrieve_group_user_ids(project_admin_group_id),
        gqr.a_retrieve_group_user_ids(project_member_group_id),
    )

    existing_proj_admin_ids: Set[str] = set(existing_proj_admin_ids_list)
    existing_proj_member_ids: Set[str] = set(existing_proj_member_ids_list)

    return (
        unique_users_map,
        project_admin_group_id,
        project_member_group_id,
        existing_proj_admin_ids,
        existing_proj_member_ids,
        vl_admin_ids_list,
    )


async def manage_user_groups(
    users_map: Dict[UUID4, AddUserToProjectIn],
    project_admin_group_id: str,
    project_member_group_id: str,
    existing_proj_admin_ids: Set[str] | None,
    existing_proj_member_ids: Set[str] | None,
    project_id: UUID4,
    vl_admin_ids_list: list[str] | None,
) -> Tuple[
    List[AddUserProjectDetails],
    List[AddUserProjectDetails],
    List[AttachUserFailedOperation],
    Dict[EmailStr, UserRoleEnum],
]:
    """
    Manage user groups by adding or updating users in project groups

    Args:
        users_map: Dictionary mapping user ID to user data
        project_admin_group_id: Project admin group ID
        project_member_group_id: Project member group ID
        existing_proj_admin_ids: Set of existing project admin user IDs
        existing_proj_member_ids: Set of existing project member user IDs
        project_id: Project ID

    Returns:
        Tuple containing:
        - added_users: List of users added to the project, each with id, email, role
        - updated_users: List of users whose roles were updated, each with id, email, role
        - failed_operations: List of failed operations
        - user_to_email_map: Dictionary mapping user email to role
    """
    umr = UserMutationRepository()
    added_users: List[AddUserProjectDetails] = []
    updated_users: List[AddUserProjectDetails] = []
    failed_operations: List[AttachUserFailedOperation] = []
    user_to_email_map: Dict[EmailStr, UserRoleEnum] = {}

    admin_ids = existing_proj_admin_ids.copy() if existing_proj_admin_ids else set()
    member_ids = existing_proj_member_ids.copy() if existing_proj_member_ids else set()

    for user_in in users_map.values():
        user_id = user_in.id
        user_id_str = str(user_id)
        requested_role = user_in.role

        is_currently_admin = user_id_str in admin_ids
        is_currently_member = user_id_str in member_ids
        is_virtual_lab_admin = (
            user_id_str in vl_admin_ids_list if vl_admin_ids_list else False
        )
        if is_virtual_lab_admin:
            # if it's virtual lab admin then no change of role should be done
            # this is priority, as in virtual lab level only have administrators (no members)
            continue

        try:
            if is_currently_admin:
                if requested_role == UserRoleEnum.admin:
                    logger.debug(
                        f"User {user_id_str} is already a project admin, skipping."
                    )
                    continue
                elif requested_role == UserRoleEnum.member:
                    logger.info(
                        "Changing role for user {} from project admin to member in project {}.".format(
                            user_id_str, project_id
                        )
                    )
                    await asyncio.gather(
                        umr.a_detach_user_from_group(
                            user_id=user_id, group_id=project_admin_group_id
                        ),
                        umr.a_attach_user_to_group(
                            user_id=user_id, group_id=project_member_group_id
                        ),
                    )
                    updated_users.append(
                        AddUserProjectDetails(
                            id=user_id_str,
                            email=user_in.email,
                            role=requested_role.value,
                        )
                    )
                    admin_ids.discard(user_id_str)
                    member_ids.add(user_id_str)
                    logger.info(
                        f"Changed role for user {user_id_str} from project admin to member. No email sent."
                    )

            elif is_currently_member:
                if requested_role == UserRoleEnum.member:
                    logger.debug(
                        f"User {user_id_str} is already a project member, skipping."
                    )
                    continue
                elif requested_role == UserRoleEnum.admin:
                    logger.info(
                        f"Changing role for user {user_id_str} from project member to admin in project {project_id}."
                    )
                    await asyncio.gather(
                        umr.a_detach_user_from_group(
                            user_id=user_id, group_id=project_member_group_id
                        ),
                        umr.a_attach_user_to_group(
                            user_id=user_id, group_id=project_admin_group_id
                        ),
                    )
                    updated_users.append(
                        AddUserProjectDetails(
                            id=user_id_str,
                            email=user_in.email,
                            role=requested_role.value,
                        )
                    )
                    member_ids.discard(user_id_str)
                    admin_ids.add(user_id_str)
                    logger.info(
                        f"Changed role for user {user_id_str} from project member to admin. No email sent."
                    )

            else:
                if requested_role == UserRoleEnum.admin:
                    logger.info(
                        f"Attaching new user {user_id_str} as project admin to project {project_id}."
                    )
                    await umr.a_attach_user_to_group(
                        user_id=user_id, group_id=project_admin_group_id
                    )
                    added_users.append(
                        AddUserProjectDetails(
                            id=user_id_str,
                            email=user_in.email,
                            role=requested_role.value,
                        )
                    )
                    admin_ids.add(user_id_str)
                elif requested_role == UserRoleEnum.member:
                    logger.info(
                        f"Attaching new user {user_id_str} as project member to project {project_id}."
                    )
                    await umr.a_attach_user_to_group(
                        user_id=user_id, group_id=project_member_group_id
                    )
                    added_users.append(
                        AddUserProjectDetails(
                            id=user_id_str,
                            email=user_in.email,
                            role=requested_role.value,
                        )
                    )
                    member_ids.add(user_id_str)

                user_to_email_map[user_in.email] = requested_role

        except KeycloakError as kc_op_err:
            error_detail = "Unknown Keycloak Error during operation"
            try:
                error_detail = loads(kc_op_err.error_message).get("error", error_detail)
            except Exception:
                pass
            logger.error(
                f"Keycloak error processing user {user_id_str} for project role {requested_role.value} in project {project_id}: {error_detail}"
            )
            failed_operations.append(
                AttachUserFailedOperation(
                    user_id=user_id,
                    requested_role=requested_role,
                    error=str(error_detail),
                )
            )
        except Exception as op_err:
            logger.error(
                f"Unexpected error processing user {user_id_str} for project role {requested_role.value} in project {project_id}: {op_err}"
            )
            failed_operations.append(
                AttachUserFailedOperation(
                    user_id=user_id,
                    requested_role=requested_role,
                    error=str(op_err),
                )
            )

    return (
        added_users,
        updated_users,
        failed_operations,
        user_to_email_map,
    )


async def send_project_emails(
    user_to_email_map: Dict[EmailStr, UserRoleEnum],
    project_id: UUID4,
    project_name: str,
    virtual_lab_id: UUID4,
    virtual_lab_name: str,
    inviter_name: str,
) -> List[EmailFailure]:
    """
    Send emails to users added to project

    Args:
        user_to_email_map: Dictionary mapping user email to role
        project_id: Project ID
        project_name: Project name
        virtual_lab_id: Virtual lab ID
        virtual_lab_name: Virtual lab name
        inviter_name: Name of the user who initiated the invitation

    Returns:
        List of failed email operations
    """
    email_failures: List[EmailFailure] = []

    try:
        for email, role in user_to_email_map.items():
            await send_add_member_to_project_email(
                EmailDetails(
                    lab_name=virtual_lab_name,
                    project_name=project_name,
                    recipient=email,
                    inviter_name=inviter_name,
                    lab_id=virtual_lab_id,
                    project_id=project_id,
                )
            )
            logger.info(
                f"Email sent to {email} for project {project_id} with role {role.value}"
            )
    except Exception as email_err:
        logger.error(
            f"Error sending email to users for project {project_id}: {email_err}"
        )
        for email in user_to_email_map.keys():
            email_failures.append(
                EmailFailure(
                    email=email,
                    error=str(email_err),
                )
            )

    return email_failures
