"""Create a course.

Orchestrates the creation of a course by:
1. Creating a virtual lab with COURSE_LAB_POLICY
2. Inserting the course record linked to that virtual lab
"""

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.ledger.modules.virtual_lab import COURSE_LAB_POLICY
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseCreateBody, CourseOut
from virtual_labs.domain.labs import VirtualLabCreate
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.usecases.labs.create_virtual_lab import create_virtual_lab


async def create_course(
    db: AsyncSession,
    payload: CourseCreateBody,
    auth: tuple[AuthUserGrants, str],
) -> VliAppResponse[CourseOut]:
    # Step 1: Create the underlying virtual lab using the course policy
    vlab_draft = VirtualLabCreate(
        name=payload.name,
        description=payload.description,
        reference_email=payload.reference_email,
        entity=payload.entity,
        compute_cell=payload.compute_cell,
    )

    vlab = await create_virtual_lab(
        db,
        virtual_lab_draft=vlab_draft,
        auth=auth,
        policy=COURSE_LAB_POLICY,
    )

    # TODO: Step 2 - Insert the course record linked to vlab.id
    raise NotImplementedError("Course record insertion not yet implemented")
