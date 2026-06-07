from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseCreateBody, CourseOut
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.usecases import course as usecases

router = APIRouter(prefix="/courses", tags=["Course Endpoints"])


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
