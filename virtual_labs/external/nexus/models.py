from datetime import datetime
from typing import Annotated, Any, List, TypedDict

from pydantic import UUID4, AnyUrl, BaseModel, Field


class NexusContext:
    context: Annotated[List[AnyUrl], Field(alias="@context")] = []


class NexusBase(BaseModel, NexusContext):
    id: Annotated[AnyUrl | str, Field(alias="@id")]
    type: Annotated[str | List[str], Field(alias="@type")]
    _createdAt: datetime
    _createdBy: datetime
    _deprecated: bool
    _self: str
    _rev: str


class NexusProject(NexusBase):
    _label: str
    _uuid: UUID4
    vocab: str
    base: str


class NexusApiMapping(TypedDict):
    namespace: str
    prefix: str


class NexusIdentity(TypedDict):
    realm: str


class NexusResource(NexusBase):
    apiMappings: Annotated[List[NexusApiMapping], Field(default=List)] = []


class NexusAcls(NexusBase):
    type: Annotated[str | List[str], Field(alias="@type")] = "AccessControlList"


class NexusAclResult(NexusBase):
    id: Annotated[AnyUrl | str, Field(alias="@id")] = ""
    type: Annotated[str | List[str], Field(alias="@type")] = "AccessControlList"


class NexusAclIdentity:
    id: Annotated[AnyUrl | str, Field(alias="@id")]
    type: Annotated[str, Field(alias="@type")]
    realm: str
    group: str


class NexusAcl:
    identity: NexusAclIdentity
    permissions: List[str]


class NexusAclList(NexusBase, NexusContext):
    _total: int
    acl: List[NexusAcl]


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
