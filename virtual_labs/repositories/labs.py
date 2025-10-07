from pydantic import UUID4, EmailStr
from sqlalchemy import false, func, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload
from sqlalchemy.sql import and_, or_

from virtual_labs.core.types import PaginatedDbResult
from virtual_labs.domain import labs
from virtual_labs.domain.common import DbPagination, PageParams
from virtual_labs.infrastructure.db.models import Project, VirtualLab


class VirtualLabDbCreate(labs.VirtualLabCreate):
    id: UUID4
    owner_id: UUID4
    admin_group_id: str
    member_group_id: str


async def get_paginated_virtual_labs(
    db: AsyncSession, page_params: PageParams, group_ids: list[str]
) -> PaginatedDbResult[list[VirtualLab]]:
    count_query = paginated_query = select(VirtualLab).where(
        and_(
            ~VirtualLab.deleted,
            or_(
                (VirtualLab.admin_group_id.in_(group_ids)),
                (VirtualLab.member_group_id.in_(group_ids)),
            ),
        )
    )
    count = await db.scalar(
        select(func.count()).select_from(count_query.options(noload("*")).subquery())
    )
    paginated_query = select(VirtualLab).where(
        and_(
            ~VirtualLab.deleted,
            or_(
                (VirtualLab.admin_group_id.in_(group_ids)),
                (VirtualLab.member_group_id.in_(group_ids)),
            ),
        )
    )

    result = (
        (
            await db.execute(
                statement=paginated_query.order_by(
                    VirtualLab.created_at.desc(), VirtualLab.updated_at.desc()
                )
                .offset((page_params.page - 1) * page_params.size)
                .limit(page_params.size)
            )
        )
        .unique()
        .scalars()
        .all()
    )

    return PaginatedDbResult(
        count=count or 0,
        rows=list(result),
    )


async def get_undeleted_virtual_lab(db: AsyncSession, lab_id: UUID4) -> VirtualLab:
    """Returns non-deleted virtual lab by id. Raises an exception if the lab by id is not found or if it is deleted."""
    query = select(VirtualLab).where(VirtualLab.id == lab_id, ~VirtualLab.deleted)
    return (await db.execute(statement=query)).unique().scalar_one()


async def get_virtual_lab_by_definition_tuple(
    db: AsyncSession, owner_id: UUID4, name: str, email: EmailStr
) -> VirtualLab | None:
    """Returns a non-deleted virtual lab matching the owner_id, and name."""
    result = await db.execute(
        select(VirtualLab).filter(
            VirtualLab.owner_id == owner_id,
            VirtualLab.reference_email == email,
            VirtualLab.name == name,
            ~VirtualLab.deleted,
        )
    )

    return result.scalar_one_or_none()


async def get_virtual_lab_soft(db: AsyncSession, lab_id: UUID4) -> VirtualLab | None:
    query = select(VirtualLab).where(VirtualLab.id == lab_id)
    return (await db.execute(statement=query)).scalar()


async def get_virtual_lab_async(db: AsyncSession, lab_id: UUID4) -> VirtualLab:
    """Returns virtual lab by id. Raises an exception if the lab by id is not found.
    The returned virtual lab might be deleted (i.e. Virtual.deleted might be True).
    """
    lab = await db.get(VirtualLab, lab_id)
    if lab is None:
        raise NoResultFound
    return lab


async def create_virtual_lab(db: AsyncSession, lab: VirtualLabDbCreate) -> VirtualLab:
    db_lab = VirtualLab(
        id=lab.id,
        owner_id=lab.owner_id,
        admin_group_id=lab.admin_group_id,
        member_group_id=lab.member_group_id,
        name=lab.name,
        description=lab.description,
        reference_email=lab.reference_email,
        projects=[],
        entity=lab.entity,
    )
    db.add(db_lab)
    await db.commit()
    await db.refresh(db_lab)
    return db_lab


async def update_virtual_lab(
    db: AsyncSession, lab_id: UUID4, lab: labs.VirtualLabUpdate
) -> VirtualLab:
    current = await get_undeleted_virtual_lab(db, lab_id)
    data_to_update = lab.model_dump(exclude_unset=True)
    query = (
        update(VirtualLab)
        .where(VirtualLab.id == lab_id)
        .values(
            {
                "name": data_to_update.get("name", current.name),
                "description": data_to_update.get("description", current.description),
                "reference_email": data_to_update.get(
                    "reference_email", current.reference_email
                ),
                "updated_at": func.now(),
                "entity": data_to_update.get("entity", current.entity),
            }
        )
    )
    await db.execute(statement=query)
    await db.commit()
    return await get_undeleted_virtual_lab(db, lab_id)


async def delete_virtual_lab(
    db: AsyncSession, lab_id: UUID4, user_id: UUID4
) -> VirtualLab:
    now = func.now()
    # Mark virtual lab as deleted
    await db.execute(
        update(VirtualLab)
        .where(VirtualLab.id == lab_id)
        .values(deleted=True, deleted_at=now, deleted_by=user_id)
    )
    # Mark projects for the virtual lab as deleted
    await db.execute(
        update(Project)
        .where(Project.virtual_lab_id == lab_id)
        .values(deleted=True, deleted_at=now, deleted_by=user_id)
    )

    await db.commit()

    return await get_virtual_lab_async(db, lab_id)


async def count_virtual_labs_with_name(db: AsyncSession, name: str) -> int:
    query = select(VirtualLab).filter(
        ~VirtualLab.deleted,
        func.lower(VirtualLab.name) == func.lower(name),
    )
    count = await db.scalar(
        select(func.count()).select_from(query.options(noload("*")).subquery())
    )
    if count is None:
        return 0
    return count


async def get_virtual_labs_with_matching_name(
    db: AsyncSession, term: str, group_ids: list[str]
) -> list[VirtualLab]:
    query = select(VirtualLab).filter(
        and_(
            ~VirtualLab.deleted,
            func.lower(VirtualLab.name).like(f"%{term.strip().lower()}%"),
            or_(
                (VirtualLab.admin_group_id.in_(group_ids)),
                (VirtualLab.member_group_id.in_(group_ids)),
            ),
        )
    )
    result = (await db.execute(statement=query)).unique().scalars().all()
    return list(result)


async def get_user_virtual_lab(db: AsyncSession, owner_id: UUID4) -> VirtualLab | None:
    """Returns the virtual lab by owner_id"""
    stmt = select(VirtualLab).where(
        VirtualLab.owner_id == owner_id,
        VirtualLab.deleted == false(),
    )
    result = await db.execute(stmt)
    vlab = result.scalars().first()

    return vlab


async def get_virtual_labs_in_list(
    db: AsyncSession,
    group_ids: list[str],
    page_params: PageParams,
    query: str | None = None,
) -> DbPagination[VirtualLab]:
    base_filter_conditions = and_(
        ~VirtualLab.deleted,
        or_(
            (VirtualLab.admin_group_id.in_(group_ids)),
            (VirtualLab.member_group_id.in_(group_ids)),
        ),
    )

    total_count_query = select(func.count(VirtualLab.id)).where(base_filter_conditions)
    total = await db.scalar(total_count_query) or 0

    final_filter_conditions = base_filter_conditions
    filtered_total = total
    if query:
        final_filter_conditions = and_(
            base_filter_conditions,
            func.lower(VirtualLab.name).ilike(f"%{query.strip().lower()}%"),
        )
        filtered_total_count_query = select(func.count(VirtualLab.id)).where(
            final_filter_conditions
        )
        filtered_total = await db.scalar(filtered_total_count_query) or 0

    paginated_query = (
        select(VirtualLab)
        .where(final_filter_conditions)
        .order_by(VirtualLab.created_at.desc(), VirtualLab.updated_at.desc())
        .offset((page_params.page - 1) * page_params.size)
        .limit(page_params.size)
    )

    result = await db.execute(statement=paginated_query)
    labs_list = list(result.scalars().all())

    page_size = len(labs_list)
    has_next = (page_params.page * page_params.size) < total
    has_previous = page_params.page > 1

    return DbPagination(
        total=total,
        filtered_total=filtered_total,
        page=page_params.page,
        size=page_params.size,
        page_size=page_size,
        results=labs_list,
        has_next=has_next,
        has_previous=has_previous,
    )


async def get_virtual_lab_stats(
    db: AsyncSession,
    virtual_lab_id: UUID4,
) -> dict[str, int]:
    """Get statistics for a virtual lab including total projects and pending invites using a single optimized query."""
    from sqlalchemy import distinct, func, select

    from virtual_labs.infrastructure.db.models import (
        Project,
        VirtualLab,
        VirtualLabInvite,
    )

    # Filter VirtualLab first
    base_query = (
        select(VirtualLab).where(
            VirtualLab.id == virtual_lab_id,
            ~VirtualLab.deleted,
        )
    ).subquery()

    stats_query = (
        select(
            base_query.c.id,
            func.count(distinct(Project.id))
            .filter(~Project.deleted)
            .label("total_projects"),
            func.count(distinct(VirtualLabInvite.id))
            .filter(~VirtualLabInvite.accepted)
            .label("total_pending_invites"),
        )
        .select_from(base_query)
        .outerjoin(Project, base_query.c.id == Project.virtual_lab_id)
        .outerjoin(VirtualLabInvite, base_query.c.id == VirtualLabInvite.virtual_lab_id)
        .group_by(base_query.c.id)
    )

    result = await db.execute(stats_query)
    stats = result.first()

    if not stats:
        return {"total_projects": 0, "total_pending_invites": 0}

    return {
        "total_projects": stats.total_projects,
        "total_pending_invites": stats.total_pending_invites,
    }


async def get_virtual_labs_where_user_is_member(
    db: AsyncSession, user_id: UUID4
) -> list[VirtualLab]:
    """Returns a list of non-deleted virtual labs where the user is a member but not the owner."""
    from virtual_labs.repositories.group_repo import GroupQueryRepository

    # Get the user's groups
    group_repo = GroupQueryRepository()
    user_groups = await group_repo.a_retrieve_user_groups(user_id=str(user_id))
    group_ids = [g.id for g in user_groups if "vlab" in g.name]

    # Get the virtual labs where user is a member of admin or member groups but not the owner
    query = select(VirtualLab).where(
        and_(
            ~VirtualLab.deleted,
            VirtualLab.owner_id != user_id,  # Not the owner
            or_(
                (VirtualLab.admin_group_id.in_(group_ids)),
                (VirtualLab.member_group_id.in_(group_ids)),
            ),
        )
    )
    result = (await db.execute(statement=query)).unique().scalars().all()

    return list(result)
