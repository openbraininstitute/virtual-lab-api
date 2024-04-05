from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Plan
from virtual_labs.repositories import plans


async def all_plans(db: AsyncSession) -> list[Plan]:
    return await plans.get_all_plans(db)
