from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import default_session_factory

DBSessionDependency = Annotated[AsyncSession, Depends(default_session_factory)]
