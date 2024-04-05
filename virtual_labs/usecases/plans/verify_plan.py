from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.repositories import plans


async def verify_plan(db: AsyncSession, plan_id: int) -> None:
    try:
        await plans.get_plan(db, plan_id)
    except NoResultFound:
        raise ValueError("Plan with id {} does not exist".format(plan_id))
