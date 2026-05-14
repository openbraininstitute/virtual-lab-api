from enum import Enum


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
