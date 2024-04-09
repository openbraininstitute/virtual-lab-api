from typing import Literal

from pydantic import UUID4, BaseModel

from virtual_labs.infrastructure.email.email_utils import InviteOrigin


class InviteOut(BaseModel):
    invite_id: UUID4
    virtual_lab_id: UUID4
    project_id: UUID4 | None
    origin: InviteOrigin
    accepted: Literal["accepted", "already_accepted"] | None
