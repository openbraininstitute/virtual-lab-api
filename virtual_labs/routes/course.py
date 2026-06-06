from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseCreateBody, CourseOut
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
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
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> VliAppResponse[CourseOut]:
    return await usecases.create_course(session, payload, auth)
