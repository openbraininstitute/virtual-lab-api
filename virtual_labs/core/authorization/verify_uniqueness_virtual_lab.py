from http import HTTPStatus

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.labs import get_user_virtual_lab
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def verify_uniq_virtual_lab(
    db: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> None:
    """Dependency that raises if the authenticated user already owns a virtual lab."""
    owner_id = get_user_id_from_auth(auth)
    existing = await get_user_virtual_lab(db=db, owner_id=owner_id)

    if existing is not None:
        raise VliError(
            message="User already has a virtual lab",
            error_code=VliErrorCode.FORBIDDEN_OPERATION,
            http_status_code=HTTPStatus.FORBIDDEN,
        )
