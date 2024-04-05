from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.labs import Labs, VirtualLabWithProject
from virtual_labs.repositories import labs as respository


async def search_virtual_labs_by_name(term: str, db: AsyncSession) -> Labs:
    matching_labs = [
        VirtualLabWithProject.model_validate(lab)
        for lab in await respository.get_virtual_labs_with_matching_name(db, term)
    ]
    # TODO: Filter labs for user
    return Labs(virtual_labs=matching_labs)
