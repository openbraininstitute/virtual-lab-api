from pydantic import UUID4, BaseModel


class VlabAccount(BaseModel):
    id: UUID4
    name: str


class ProjAccount(BaseModel):
    id: UUID4
    name: str


class VlabAccountCreationResponse(BaseModel):
    message: str
    data: VlabAccount


class ProjAccountCreationResponse(BaseModel):
    message: str
    data: ProjAccount
