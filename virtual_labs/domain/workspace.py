from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel

from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.project import ProjectVlOut
from virtual_labs.domain.user import Workspace


class RecentWorkspaceOutWithDetails(BaseModel):
    """Response model for recent workspace with full virtual lab and project details"""

    user_id: UUID4
    workspace: Optional[Workspace] = None
    updated_at: Optional[datetime] = None
    virtual_lab: Optional[VirtualLabDetails] = None
    project: Optional[ProjectVlOut] = None

    model_config = {"from_attributes": True}


class RecentWorkspaceResponseWithDetails(BaseModel):
    """API response wrapper for recent workspace with full details"""

    recent_workspace: RecentWorkspaceOutWithDetails
