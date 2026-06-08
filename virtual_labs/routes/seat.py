from datetime import datetime
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import (
    ListSeatsResponse,
    ProvisionSeatsBody,
    ProvisionSeatsResponse,
    SeatBatchSearchResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.usecases import seat as usecases

router = APIRouter(prefix="/seats", tags=["Seat Endpoints"])


@router.post(
    "/provision",
    operation_id="provision_seats",
    summary="Provision seats for a course",
    response_model=VliAppResponse[ProvisionSeatsResponse],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def provision_seats_endpoint(
    payload: ProvisionSeatsBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[ProvisionSeatsResponse]:
    return await usecases.provision_seats(session, payload)


@router.get(
    "/batches/{batch_id}",
    operation_id="get_seat_batch",
    summary="Get a seat batch by ID",
    response_model=SeatBatchSearchResponse,
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def get_seat_batch_endpoint(
    batch_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> SeatBatchSearchResponse:
    return await usecases.get_seat_batch_by_id(session, batch_id)


@router.get(
    "/batches",
    operation_id="search_seat_batches",
    summary="Search seat batches with filters",
    response_model=SeatBatchSearchResponse,
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def search_seat_batches_endpoint(
    course_id: Optional[UUID4] = Query(None, description="Filter by course ID"),
    institution_id: Optional[UUID4] = Query(
        None, description="Filter by institution ID"
    ),
    vlab_name: Optional[str] = Query(
        None, description="Filter by virtual lab name (partial match)"
    ),
    institution_name: Optional[str] = Query(
        None, description="Filter by institution name (partial match)"
    ),
    created_after: Optional[datetime] = Query(
        None, description="Filter batches created after this date"
    ),
    created_before: Optional[datetime] = Query(
        None, description="Filter batches created before this date"
    ),
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> SeatBatchSearchResponse:
    return await usecases.search_seat_batches(
        session,
        course_id=course_id,
        institution_id=institution_id,
        vlab_name=vlab_name,
        institution_name=institution_name,
        created_after=created_after,
        created_before=created_before,
    )


@router.get(
    "/courses/{course_id}",
    operation_id="list_seats_for_course",
    summary="List seats for a course (vlab admin)",
    response_model=ListSeatsResponse,
)
async def list_seats_endpoint(
    course_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> ListSeatsResponse:
    user, _token = auth

    result = await session.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None or not user.is_vlab_admin(course.virtual_lab_id):
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
            message="Not authorized to perform this action",
        )

    return await usecases.list_seats(session, course_id)
