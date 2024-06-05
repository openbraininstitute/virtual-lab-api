from enum import Enum
from typing import TypedDict

from pydantic import UUID4, BaseModel


class BookmarkCategory(Enum):
    ExperimentalBoutonDensity = "ExperimentsBoutonDensity"
    ExperimentalNeuronDensity = "ExperimentalNeuronDensity"
    ExperimentalElectroPhysiology = "ExperimentalElectroPhysiology"
    ExperimentalSynapsePerConnection = "ExperimentalSynapsePerConnection"
    ExperimentalNeuronMorphology = "ExperimentalNeuronMorphology"
    SimulationCampaigns = "SimulationCampaign"
    CircuitEModel = "CircuitEModel"


class BookmarkIn(BaseModel):
    resource_id: str
    category: BookmarkCategory

    class Config:
        from_attributes = True


class BookmarkOut(BaseModel):
    id: UUID4
    resource_id: str
    category: BookmarkCategory

    class Config:
        from_attributes = True


BulkDeleteBookmarks = TypedDict(
    "BulkDeleteBookmarks",
    {
        "successfully_deleted": list[BookmarkIn],
        "failed_to_delete": list[BookmarkIn],
    },
)
