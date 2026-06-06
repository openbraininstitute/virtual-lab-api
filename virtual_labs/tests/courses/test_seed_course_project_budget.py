"""Tests for seed_course_project_budget logic."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from virtual_labs.usecases.project.create_new_project import seed_course_project_budget


def _make_virtual_lab(*, has_course: bool) -> MagicMock:
    vlab = MagicMock()
    vlab.id = uuid4()
    vlab.course = MagicMock() if has_course else None
    return vlab


@pytest.mark.asyncio
@patch("virtual_labs.usecases.project.create_new_project.settings")
@patch("virtual_labs.usecases.project.create_new_project.accounting_cases")
async def test_tops_up_and_assigns_when_vlab_has_course(
    mock_accounting: MagicMock,
    mock_settings: MagicMock,
) -> None:
    mock_settings.ACCOUNTING_BASE_URL = "http://accounting:8000"
    mock_accounting.top_up_virtual_lab_budget = AsyncMock()
    mock_accounting.assign_project_budget = AsyncMock()

    vlab = _make_virtual_lab(has_course=True)
    project_id = uuid4()

    result = await seed_course_project_budget(vlab, project_id=project_id)

    assert result is True
    mock_accounting.top_up_virtual_lab_budget.assert_awaited_once_with(
        virtual_lab_id=vlab.id,
        amount=200.0,
    )
    mock_accounting.assign_project_budget.assert_awaited_once_with(
        virtual_lab_id=vlab.id,
        project_id=project_id,
        amount=200.0,
    )


@pytest.mark.asyncio
@patch("virtual_labs.usecases.project.create_new_project.settings")
@patch("virtual_labs.usecases.project.create_new_project.accounting_cases")
async def test_skips_when_vlab_has_no_course(
    mock_accounting: MagicMock,
    mock_settings: MagicMock,
) -> None:
    mock_settings.ACCOUNTING_BASE_URL = "http://accounting:8000"
    mock_accounting.top_up_virtual_lab_budget = AsyncMock()
    mock_accounting.assign_project_budget = AsyncMock()

    vlab = _make_virtual_lab(has_course=False)
    project_id = uuid4()

    result = await seed_course_project_budget(vlab, project_id=project_id)

    assert result is False
    mock_accounting.top_up_virtual_lab_budget.assert_not_awaited()
    mock_accounting.assign_project_budget.assert_not_awaited()


@pytest.mark.asyncio
@patch("virtual_labs.usecases.project.create_new_project.settings")
@patch("virtual_labs.usecases.project.create_new_project.accounting_cases")
async def test_skips_when_accounting_url_not_configured(
    mock_accounting: MagicMock,
    mock_settings: MagicMock,
) -> None:
    mock_settings.ACCOUNTING_BASE_URL = None
    mock_accounting.top_up_virtual_lab_budget = AsyncMock()
    mock_accounting.assign_project_budget = AsyncMock()

    vlab = _make_virtual_lab(has_course=True)
    project_id = uuid4()

    result = await seed_course_project_budget(vlab, project_id=project_id)

    assert result is False
    mock_accounting.top_up_virtual_lab_budget.assert_not_awaited()
    mock_accounting.assign_project_budget.assert_not_awaited()


@pytest.mark.asyncio
@patch("virtual_labs.usecases.project.create_new_project.settings")
@patch("virtual_labs.usecases.project.create_new_project.accounting_cases")
async def test_returns_false_on_accounting_failure(
    mock_accounting: MagicMock,
    mock_settings: MagicMock,
) -> None:
    mock_settings.ACCOUNTING_BASE_URL = "http://accounting:8000"
    mock_accounting.top_up_virtual_lab_budget = AsyncMock(
        side_effect=Exception("accounting down")
    )

    vlab = _make_virtual_lab(has_course=True)
    project_id = uuid4()

    result = await seed_course_project_budget(vlab, project_id=project_id)

    assert result is False
