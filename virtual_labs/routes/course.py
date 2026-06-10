from fastapi import APIRouter, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.core.authorization.verify_course_admin import verify_course_admin
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import (
    AssignSeatResponse,
    AssignSeatsBody,
    CourseCreateBody,
    CourseDetailOut,
    CourseOut,
    CourseUpdateBody,
    DropSeatResponse,
    DropSeatsBody,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.usecases import course as usecases

router = APIRouter(prefix="/courses", tags=["Course Endpoints"])


@router.get(
    "",
    operation_id="search_courses",
    summary="Search courses by virtual lab name",
    response_model=VliAppResponse[list[CourseDetailOut]],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def search_courses_endpoint(
    vlab_name: str = Query(..., min_length=1, description="Virtual lab name to search"),
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[list[CourseDetailOut]]:
    return await usecases.search_courses_by_vlab_name(session, vlab_name)


@router.get(
    "/{course_id}",
    operation_id="get_course",
    summary="Get a course by ID",
    response_model=VliAppResponse[CourseDetailOut],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def get_course_endpoint(
    course_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[CourseDetailOut]:
    return await usecases.get_course_by_id(session, course_id)


@router.post(
    "",
    operation_id="create_course",
    summary="Create a new course",
    response_model=VliAppResponse[CourseOut],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def create_course_endpoint(
    payload: CourseCreateBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[CourseOut]:
    return await usecases.create_course(session, payload, auth)


@router.patch(
    "/{course_id}",
    operation_id="update_course",
    summary="Update a draft course",
    response_model=VliAppResponse[CourseOut],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def update_course_endpoint(
    course_id: UUID4,
    payload: CourseUpdateBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[CourseOut]:
    return await usecases.update_course(session, course_id, payload, auth)


@router.post(
    "/{course_id}/activate",
    operation_id="activate_course",
    summary="Activate a course",
    response_model=VliAppResponse[CourseOut],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def activate_course_endpoint(
    course_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[CourseOut]:
    return await usecases.activate_course(session, course_id, auth)


@router.post(
    "/{course_id}/void",
    operation_id="void_course",
    summary="Void a course",
    response_model=VliAppResponse[CourseOut],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def void_course_endpoint(
    course_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[CourseOut]:
    return await usecases.void_course(session, course_id, auth)


@router.post(
    "/{course_id}/assign_seats",
    operation_id="assign_seats",
    summary="Assign available seats to a list of students (creates an enrolment per seat)",
    response_model=AssignSeatResponse,
)
async def assign_seats_endpoint(
    course_id: UUID4,
    payload: AssignSeatsBody,
    grant: tuple[AuthUserGrants, Course] = Depends(verify_course_admin),
    session: AsyncSession = Depends(default_session_factory),
) -> AssignSeatResponse:
    _user, course = grant
    results = await usecases.assign_seats(
        session, course=course, students=payload.students
    )
    return AssignSeatResponse(results=results)


@router.post(
    "/{course_id}/drop_seats",
    operation_id="drop_seats",
    summary="Drop (release) seats for students in a course",
    response_model=DropSeatResponse,
)
async def drop_seats_endpoint(
    course_id: UUID4,
    payload: DropSeatsBody,
    grant: tuple[AuthUserGrants, Course] = Depends(verify_course_admin),
    session: AsyncSession = Depends(default_session_factory),
) -> DropSeatResponse:
    _user, course = grant
    results = await usecases.drop_seats(session, course=course, payload=payload)
    return DropSeatResponse(results=results)
