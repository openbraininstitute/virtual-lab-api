from fastapi import APIRouter, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.core.authorization.verify_course_admin import verify_course_admin
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import (
    ActivateEnrolmentResult,
    ActivateEnrolmentsResponse,
    ClaimCourseSummary,
    ClaimEnrolmentBody,
    ClaimEnrolmentOut,
    CourseCreateBody,
    CourseDetailOut,
    CourseOut,
    CourseUpdateBody,
    EnrolmentOut,
    ListEnrolmentsResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
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
    "/claim",
    operation_id="claim_enrolment",
    summary="Claim an enrolment — validates the link and records who claimed it",
    response_model=VliAppResponse[ClaimEnrolmentOut],
)
async def claim_enrolment_endpoint(
    payload: ClaimEnrolmentBody,
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
    session: AsyncSession = Depends(default_session_factory),
) -> VliAppResponse[ClaimEnrolmentOut]:
    user, _ = auth
    enrolment = await usecases.claim_enrolment(
        session,
        enrolment_id=payload.enrolment_id,
        user_id=user.id,
    )
    assert enrolment.claimed_by is not None
    return VliAppResponse[ClaimEnrolmentOut](
        message="Enrolment claimed successfully",
        data=ClaimEnrolmentOut(
            id=enrolment.id,
            course_id=enrolment.course_id,
            project_id=enrolment.project_id,
            contact_email=enrolment.contact_email,
            student_id=enrolment.student_id,
            claimed_by=enrolment.claimed_by,
            course=ClaimCourseSummary(
                id=enrolment.course.id,
                virtual_lab_id=enrolment.course.virtual_lab_id,
                virtual_lab_name=enrolment.course.virtual_lab.name,
                institution_name=enrolment.course.institution.name,
                start_date=enrolment.course.start_date,
                end_date=enrolment.course.end_date,
            ),
        ),
    )


@router.post(
    "/activate-enrolments",
    operation_id="activate_enrolments",
    summary="Activate all pending enrolments for the authenticated user (adds to KC groups)",
    response_model=ActivateEnrolmentsResponse,
)
async def activate_enrolments_endpoint(
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
    session: AsyncSession = Depends(default_session_factory),
) -> ActivateEnrolmentsResponse:
    user, _ = auth
    results = await usecases.activate_enrolments(
        session,
        user_id=user.id,
    )
    return ActivateEnrolmentsResponse(
        results=[ActivateEnrolmentResult(**r) for r in results]
    )


@router.delete(
    "/{course_id}",
    operation_id="delete_course",
    summary="Delete a course — drops all students, depletes budget, removes course and seats (vlab admin only)",
    response_model=VliAppResponse[None],
)
async def delete_course_endpoint(
    grant: tuple[AuthUserGrants, Course] = Depends(verify_course_admin),
    session: AsyncSession = Depends(default_session_factory),
) -> VliAppResponse[None]:
    _user, course = grant
    return await usecases.delete_course(session, course.id)


@router.get(
    "/{course_id}/enrolments",
    operation_id="list_enrolments",
    summary="List all enrolments for a course (vlab admin)",
    response_model=ListEnrolmentsResponse,
)
async def list_enrolments_endpoint(
    course_id: UUID4,
    grant: tuple[AuthUserGrants, Course] = Depends(verify_course_admin),
    session: AsyncSession = Depends(default_session_factory),
) -> ListEnrolmentsResponse:
    _user, course = grant
    enrolments = await usecases.list_enrolments(session, course_id=course.id)
    return ListEnrolmentsResponse(
        enrolments=[EnrolmentOut.model_validate(e) for e in enrolments]
    )
