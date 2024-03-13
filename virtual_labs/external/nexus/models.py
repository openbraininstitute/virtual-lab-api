from datetime import datetime
from typing import Annotated, Any, List, TypedDict

from pydantic import UUID4, AnyUrl, BaseModel, Field


class NexusBase(BaseModel):
    context: Annotated[List[AnyUrl], Field(alias="@context")] = []
    id: Annotated[AnyUrl | str, Field(alias="@id")] = ""
    type: Annotated[str | List[str], Field(alias="@type")] = ""
    _createdAt: datetime
    _createdBy: datetime
    _deprecated: bool
    _self: str


class NexusProject(NexusBase):
    _label: str | None = None
    _uuid: UUID4 | None = None
    vocab: str | None = None
    base: AnyUrl | None = None


class NexusApiMapping(TypedDict):
    namespace: str
    prefix: str


class NexusIdentity(TypedDict):
    realm: str


class NexusResource(NexusBase):
    apiMappings: Annotated[List[NexusApiMapping], Field(default=List)] = []


class NexusAcls(NexusBase):
    type: Annotated[str | List[str], Field(alias="@type")] = "AccessControlList"


class NexusESViewMappingPropertyType(BaseModel):
    type: str


class NexusESViewMappingProperty(TypedDict):
    dynamic: bool
    properties: dict[str, NexusESViewMappingPropertyType]


class NexusElasticSearchViewMapping(BaseModel):
    type: Annotated[str | List[str], Field(alias="@type")] = [
        "View",
        "ElasticSearchView",
    ]
    mapping: NexusESViewMappingProperty
    pipeline: Annotated[List[Any], Field(default=List)] = []
