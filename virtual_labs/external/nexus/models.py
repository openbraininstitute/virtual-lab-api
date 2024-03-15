from datetime import datetime
from typing import Annotated, Any, List, Optional, TypedDict

from pydantic import BaseModel, Field


class NexusBase(BaseModel):
    context: Annotated[List[str], Field(alias="@context")] = []
    id: Annotated[str, Field(alias="@id")]
    type: Annotated[str | List[str], Field(alias="@type")]
    createdAt: Annotated[datetime, Field(alias="_createdAt")]
    createdBy: Annotated[str, Field(alias="_createdBy")]
    deprecated: Annotated[bool, Field(alias="_deprecated")]
    self: Annotated[str, Field(alias="_self")]
    rev: Annotated[int, Field(alias="_rev")]


class NexusProject(NexusBase):
    label: Annotated[str, Field(alias="_label")]
    uuid: Annotated[int, Field(alias="_uuid")]


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
    id: Annotated[str, Field(alias="@id")] = ""
    type: Annotated[str | List[str], Field(alias="@type")] = "AccessControlList"


class NexusAclIdentity(BaseModel):
    id: Annotated[str, Field(alias="@id", default=None)]
    type: Annotated[str, Field(alias="@type", default=None)]
    realm: Optional[str] = None
    # group: Optional[str] = Field(None)


class NexusAcl(TypedDict):
    identity: NexusAclIdentity
    permissions: List[str]


class NexusAclList(BaseModel):
    acl: List[NexusAcl]
    rev: Annotated[int, Field(alias="_rev")]


class NexusResultAcl(BaseModel):
    context: Annotated[List[str], Field(alias="@context")] = []
    results: Annotated[List[NexusAclList], Field(alias="_results")]
    total: Annotated[int, Field(alias="_total")]


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
