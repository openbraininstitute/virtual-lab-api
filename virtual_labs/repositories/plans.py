from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Plan


async def get_plan(db: AsyncSession, plan_id: int) -> Plan:
    plan = await db.get(Plan, plan_id)
    # TODO: Check if this will automatically be raise or not
    if plan is None:
        raise NoResultFound
    return plan


async def get_all_plans(db: AsyncSession) -> list[Plan]:
    result = (await db.execute(select(Plan))).scalars().all()
    return list(result)
