from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_service_admin
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import ProvisionSeatsBody, ProvisionSeatsResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.usecases import seat as usecases

router = APIRouter(prefix="/seats", tags=["Seat Endpoints"])


@router.post(
    "/provision",
    operation_id="provision_seats",
    summary="Provision seats for a virtual lab",
    response_model=VliAppResponse[ProvisionSeatsResponse],
)
@verify_service_admin([VLAB_SERVICE_ADMIN_GROUP])
async def provision_seats_endpoint(
    payload: ProvisionSeatsBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[ProvisionSeatsResponse]:
    return await usecases.provision_seats(session, payload)
