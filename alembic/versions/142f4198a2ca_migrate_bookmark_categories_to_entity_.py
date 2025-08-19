"""migrate_bookmark_categories_to_entity_types

Revision ID: 142f4198a2ca
Revises: 0af36743e9f3
Create Date: 2025-08-18 14:32:23.555984

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "142f4198a2ca"
down_revision: Union[str, None] = "0af36743e9f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create new enum type with EntityType values
    op.execute(
        """
        CREATE TYPE entitytype AS ENUM(
            'analysis_software_source_code',
            'brain_atlas',
            'brain_atlas_region',
            'cell_composition',
            'electrical_cell_recording',
            'electrical_recording_stimulus',
            'emodel',
            'experimental_bouton_density',
            'experimental_neuron_density',
            'experimental_synapses_per_connection',
            'ion_channel_model',
            'memodel',
            'mesh',
            'memodel_calibration_result',
            'me_type_density',
            'publication',
            'reconstruction_morphology',
            'simulation',
            'simulation_campaign',
            'simulation_campaign_generation',
            'simulation_execution',
            'simulation_result',
            'scientific_artifact',
            'single_neuron_simulation',
            'single_neuron_synaptome',
            'single_neuron_synaptome_simulation',
            'subject',
            'validation_result',
            'circuit'
        )
    """
    )

    # Add temporary column with new enum type
    op.execute("ALTER TABLE bookmark ADD COLUMN category_new entitytype")

    # Migrate data from old enum to new enum using mapping
    migrations = [
        ("ExperimentalBoutonDensity", "experimental_bouton_density"),
        ("ExperimentalNeuronDensity", "experimental_neuron_density"),
        ("ExperimentalElectroPhysiology", "electrical_cell_recording"),
        ("ExperimentalSynapsePerConnection", "experimental_synapses_per_connection"),
        ("ExperimentalNeuronMorphology", "reconstruction_morphology"),
        ("SimulationCampaign", "simulation_campaign"),
        ("CircuitEModel", "emodel"),
        ("CircuitMEModel", "memodel"),
        ("SingleNeuronSynaptome", "single_neuron_synaptome"),
        ("SingleNeuronSimulation", "single_neuron_simulation"),
        ("SynaptomeSimulation", "single_neuron_synaptome_simulation"),
    ]

    for old_value, new_value in migrations:
        op.execute(
            f"""
            UPDATE bookmark 
            SET category_new = '{new_value}' 
            WHERE category = '{old_value}'
        """
        )

    # Drop old unique constraint (resource_id based)
    op.drop_constraint(
        "bookmark_unique_for_resource_category_per_project", "bookmark", type_="unique"
    )

    # Drop resource_id column (no longer used in new model)
    op.drop_index("ix_bookmark_resource_id", table_name="bookmark")
    op.drop_column("bookmark", "resource_id")

    # Drop old column and rename new column
    op.execute("ALTER TABLE bookmark DROP COLUMN category")
    op.execute("ALTER TABLE bookmark RENAME COLUMN category_new TO category")

    # Set NOT NULL constraint on category column
    op.execute("ALTER TABLE bookmark ALTER COLUMN category SET NOT NULL")

    # Create new unique constraint (entity_id based)
    op.create_unique_constraint(
        "bookmark_unique_for_entity_category_per_project",
        "bookmark",
        ["entity_id", "category", "project_id"],
    )

    # Drop old enum type
    op.execute("DROP TYPE bookmarkcategory")


def downgrade() -> None:
    # Recreate old enum type
    op.execute(
        """
        CREATE TYPE bookmarkcategory AS ENUM(
            'ExperimentalBoutonDensity',
            'ExperimentalNeuronDensity', 
            'ExperimentalElectroPhysiology',
            'ExperimentalSynapsePerConnection',
            'ExperimentalNeuronMorphology',
            'SimulationCampaign',
            'CircuitEModel',
            'CircuitMEModel',
            'SingleNeuronSynaptome',
            'SingleNeuronSimulation',
            'SynaptomeSimulation'
        )
    """
    )

    # Add temporary column with old enum type
    op.execute("ALTER TABLE bookmark ADD COLUMN category_old bookmarkcategory")

    # Migrate data back from new enum to old enum
    reverse_migrations = [
        ("experimental_bouton_density", "ExperimentalBoutonDensity"),
        ("experimental_neuron_density", "ExperimentalNeuronDensity"),
        ("electrical_cell_recording", "ExperimentalElectroPhysiology"),
        ("experimental_synapses_per_connection", "ExperimentalSynapsePerConnection"),
        ("reconstruction_morphology", "ExperimentalNeuronMorphology"),
        ("simulation_campaign", "SimulationCampaign"),
        ("emodel", "CircuitEModel"),
        ("memodel", "CircuitMEModel"),
        ("single_neuron_synaptome", "SingleNeuronSynaptome"),
        ("single_neuron_simulation", "SingleNeuronSimulation"),
        ("single_neuron_synaptome_simulation", "SynaptomeSimulation"),
    ]

    for new_value, old_value in reverse_migrations:
        op.execute(
            f"""
            UPDATE bookmark 
            SET category_old = '{old_value}' 
            WHERE category = '{new_value}'
        """
        )

    # Drop new unique constraint (entity_id based)
    op.drop_constraint(
        "bookmark_unique_for_entity_category_per_project", "bookmark", type_="unique"
    )

    # Add back resource_id column (for old model compatibility)
    op.add_column("bookmark", sa.Column("resource_id", sa.String(), nullable=True))
    op.create_index(
        "ix_bookmark_resource_id", "bookmark", ["resource_id"], unique=False
    )

    # Drop new column and rename old column back
    op.execute("ALTER TABLE bookmark DROP COLUMN category")
    op.execute("ALTER TABLE bookmark RENAME COLUMN category_old TO category")

    # Set NOT NULL constraint on category column
    op.execute("ALTER TABLE bookmark ALTER COLUMN category SET NOT NULL")

    # Recreate old unique constraint (resource_id based)
    op.create_unique_constraint(
        "bookmark_unique_for_resource_category_per_project",
        "bookmark",
        ["resource_id", "category", "project_id"],
    )

    # Drop new enum type
    op.execute("DROP TYPE entitytype")
