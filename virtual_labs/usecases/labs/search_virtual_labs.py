from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.labs import SearchLabResponse, VirtualLabDomain
from virtual_labs.repositories import labs as respository
from virtual_labs.repositories.user_repo import UserQueryRepository


async def search_virtual_labs_by_name(
    term: str, db: AsyncSession, user_id: UUID4
) -> SearchLabResponse:
    user_repo = UserQueryRepository()
    group_ids = [group.id for group in user_repo.retrieve_user_groups(user_id)]

    matching_labs = [
        VirtualLabDomain.model_validate(lab)
        for lab in await respository.get_virtual_labs_with_matching_name(
            db, term, group_ids
        )
    ]
    return SearchLabResponse(virtual_labs=matching_labs)
