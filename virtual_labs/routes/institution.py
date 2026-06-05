from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.institution import InstitutionCreate, InstitutionOut
from virtual_labs.domain.labs import LabResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Institution
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser

router = APIRouter(prefix="/institutions", tags=["Institutions Endpoints"])


@router.post("", response_model=LabResponse[InstitutionOut])
async def create_institution(
    payload: InstitutionCreate,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[InstitutionOut]:
    institution = Institution(
        name=payload.name,
        contact_email=payload.contact_email,
    )
    session.add(institution)
    await session.commit()
    await session.refresh(institution)

    return LabResponse[InstitutionOut](
        message="Newly created institution",
        data=InstitutionOut.model_validate(institution),
    )
