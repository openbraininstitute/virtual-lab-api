from fastapi import APIRouter, Depends

from virtual_labs.domain.labs import LabResponse
from virtual_labs.domain.user import AllUsersCount
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases.users.get_count_of_all_users import get_count_of_all_users

router = APIRouter()


@router.get("/users_count", response_model=LabResponse[AllUsersCount])
async def get_all_users_count(
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[AllUsersCount]:
    return await get_count_of_all_users()
