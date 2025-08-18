from enum import StrEnum, auto
from typing import TypedDict

from pydantic import UUID4, BaseModel


class EntityType(StrEnum):
    """Entity types."""

    analysis_software_source_code = auto()
    brain_atlas = auto()
    brain_atlas_region = auto()
    cell_composition = auto()
    electrical_cell_recording = auto()
    electrical_recording_stimulus = auto()
    emodel = auto()
    experimental_bouton_density = auto()
    experimental_neuron_density = auto()
    experimental_synapses_per_connection = auto()
    ion_channel_model = auto()
    memodel = auto()
    mesh = auto()
    memodel_calibration_result = auto()
    me_type_density = auto()
    publication = auto()
    reconstruction_morphology = auto()
    simulation = auto()
    simulation_campaign = auto()
    simulation_campaign_generation = auto()
    simulation_execution = auto()
    simulation_result = auto()
    scientific_artifact = auto()
    single_neuron_simulation = auto()
    single_neuron_synaptome = auto()
    single_neuron_synaptome_simulation = auto()
    subject = auto()
    validation_result = auto()
    circuit = auto()


class BookmarkIn(BaseModel):
    entity_id: UUID4 | None = None
    category: EntityType

    class Config:
        from_attributes = True
        populate_by_name = True


class BookmarkOut(BaseModel):
    id: UUID4
    entity_id: UUID4 | None = None
    category: EntityType

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
