from http import HTTPStatus
from typing import Literal
from uuid import uuid4

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain import labs as domain
from virtual_labs.infrastructure.db import models
from virtual_labs.repositories import labs as repository
from virtual_labs.repositories.group_repo import GroupMutationRepository
from virtual_labs.repositories.user_repo import UserMutationRepository
from virtual_labs.usecases.plans.verify_plan import verify_plan

GroupIds = dict[Literal["member_group_id"] | Literal["admin_group_id"], str]


async def create_keycloak_groups(lab_id: UUID4, lab_name: str) -> GroupIds:
    kc = GroupMutationRepository()

    try:
        admin_group_id = kc.create_virtual_lab_group(
            vl_id=lab_id, vl_name=lab_name, role=UserRoleEnum.admin
        )
        member_group_id = kc.create_virtual_lab_group(
            vl_id=lab_id, vl_name=lab_name, role=UserRoleEnum.member
        )

        assert admin_group_id is not None
        assert member_group_id is not None

        return {"admin_group_id": admin_group_id, "member_group_id": member_group_id}
    except IdentityError as error:
        raise error
    except Exception as error:
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=str(error),
        )


async def create_virtual_lab(
    db: Session, lab: domain.VirtualLabCreate, owner_id: UUID4
) -> models.VirtualLab:
    try:
        verify_plan(db, lab.plan_id)
        new_lab_id = uuid4()

        # Create admin & member groups
        group_ids = await create_keycloak_groups(new_lab_id, lab.name)

        # Add user as admin for this lab
        user_repo = UserMutationRepository()
        user_repo.attach_user_to_group(
            user_id=owner_id, group_id=group_ids["admin_group_id"]
        )

        # Save lab to db
        lab_with_ids = repository.VirtualLabDbCreate(
            id=new_lab_id,
            owner_id=owner_id,
            admin_group_id=group_ids["admin_group_id"],
            member_group_id=group_ids["member_group_id"],
            **lab.model_dump(),
        )
        return repository.create_virtual_lab(db, lab_with_ids)
    except IdentityError as error:
        logger.error(
            f"Virtual lab could not be created because of idenity error {error}"
        )
        raise VliError(
            message=f"User {owner_id} is not authorized to create virtual lab",
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
        )
    except IntegrityError as error:
        logger.error(
            "Virtual lab could not be created due to database error {}".format(error)
        )
        raise VliError(
            message="Another virtual lab with same name already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
        )
    except ValueError as error:
        raise VliError(
            message=str(error),
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except SQLAlchemyError as error:
        logger.error(
            "Virtual lab could not be created due to an unknown database error {}".format(
                error
            )
        )

        raise VliError(
            message="Virtual lab could not be saved to the database",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )
    except IdentityError as error:
        raise error
    except VliError as error:
        raise error
    except Exception as error:
        logger.error(
            "Virtual lab could not be created due to an unknown error {}".format(error)
        )

        raise VliError(
            message="Virtual lab could not be created",
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
