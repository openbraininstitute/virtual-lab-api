"""Tests that create_course seeds the template project with credits via seed_course_project_budget."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from virtual_labs.usecases.course.create_course import create_course


@pytest.mark.asyncio
@patch(
    "virtual_labs.usecases.course.create_course.seed_course_project_budget",
    new_callable=AsyncMock,
)
@patch(
    "virtual_labs.usecases.course.create_course._validate_project",
    new_callable=AsyncMock,
)
@patch(
    "virtual_labs.usecases.course.create_course._validate_virtual_lab",
    new_callable=AsyncMock,
)
async def test_create_course_calls_seed_course_project_budget(
    mock_validate_vlab: AsyncMock,
    mock_validate_project: AsyncMock,
    mock_seed_budget: AsyncMock,
) -> None:
    """create_course should call seed_course_project_budget with the vlab and template project id."""
    vlab = MagicMock()
    vlab.id = uuid4()
    mock_validate_vlab.return_value = vlab
    mock_validate_project.return_value = MagicMock()

    template_project_id = uuid4()
    payload = MagicMock()
    payload.virtual_lab_id = vlab.id
    payload.template_project_id = template_project_id
    payload.institution_id = uuid4()
    payload.start_date = None
    payload.end_date = None
    payload.last_drop_date = None

    course_id = uuid4()

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def fake_refresh(obj: Any) -> None:
        obj.id = course_id
        obj.status = "draft"

    db.refresh = AsyncMock(side_effect=fake_refresh)

    auth = (MagicMock(), "token")

    await create_course(db, payload, auth)

    mock_seed_budget.assert_awaited_once_with(vlab, project_id=template_project_id)
