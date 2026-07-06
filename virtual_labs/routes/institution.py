from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.domain.institution import (
    InstitutionCreate,
    InstitutionOut,
    InstitutionUpdate,
)
from virtual_labs.domain.labs import LabResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.usecases import institution as usecases

router = APIRouter(prefix="/institutions", tags=["Institutions Endpoints"])


@router.post("", response_model=LabResponse[InstitutionOut])
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def create_institution(
    payload: InstitutionCreate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InstitutionOut]:
    result = await usecases.create_institution(session, payload)
    return LabResponse[InstitutionOut](
        message="Newly created institution",
        data=result,
    )


@router.patch("/{institution_id}", response_model=LabResponse[InstitutionOut])
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def update_institution(
    institution_id: UUID4,
    payload: InstitutionUpdate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InstitutionOut]:
    result = await usecases.update_institution(session, institution_id, payload)
    return LabResponse[InstitutionOut](
        message="Updated institution",
        data=result,
    )


@router.get(
    "/_search",
    response_model=LabResponse[list[InstitutionOut]],
    summary="Search institutions by name",
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def search_institutions(
    q: Optional[str] = Query(
        default=None, description="Search term to filter institutions by name"
    ),
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[list[InstitutionOut]]:
    results = await usecases.search_institutions_by_name(session, query=q)
    return LabResponse[list[InstitutionOut]](
        message="Institutions matching query" if q else "All institutions",
        data=results,
    )


@router.get(
    "/{institution_id}",
    response_model=LabResponse[InstitutionOut],
    summary="Get an institution by ID",
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def get_institution(
    institution_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InstitutionOut]:
    result = await usecases.get_institution_by_id(session, institution_id)
    return LabResponse[InstitutionOut](
        message="Institution found",
        data=result,
    )
