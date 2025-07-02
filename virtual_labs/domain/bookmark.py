from enum import Enum
from typing import Annotated, TypedDict

from pydantic import UUID4, BaseModel, Field


class BookmarkCategory(Enum):
    ExperimentalBoutonDensity = "ExperimentalBoutonDensity"
    ExperimentalNeuronDensity = "ExperimentalNeuronDensity"
    ExperimentalElectroPhysiology = "ExperimentalElectroPhysiology"
    ExperimentalSynapsePerConnection = "ExperimentalSynapsePerConnection"
    ExperimentalNeuronMorphology = "ExperimentalNeuronMorphology"
    SimulationCampaign = "SimulationCampaign"
    CircuitEModel = "CircuitEModel"
    CircuitMEModel = "CircuitMEModel"
    SingleNeuronSynaptome = "SingleNeuronSynaptome"
    SingleNeuronSimulation = "SingleNeuronSimulation"
    SynaptomeSimulation = "SynaptomeSimulation"


class BookmarkIn(BaseModel):
    entity_id: UUID4 | None = None
    resource_id: Annotated[str | None, Field(alias="resourceId")] = None
    category: BookmarkCategory

    class Config:
        from_attributes = True
        populate_by_name = True


class BookmarkOut(BaseModel):
    id: UUID4
    entity_id: UUID4 | None = None
    # TODO: return snake case for entity core
    resource_id: Annotated[str | None, Field(alias="resourceId")] = None
    category: BookmarkCategory

    class Config:
        from_attributes = True
        populate_by_name = True


class DeleteBookmarkIn(BookmarkIn):
    pass


BulkDeleteBookmarks = TypedDict(
    "BulkDeleteBookmarks",
    {
        "successfully_deleted": list[BookmarkIn],
        "failed_to_delete": list[BookmarkIn],
    },
)
