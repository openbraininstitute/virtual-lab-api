"""add simulation camapign to bookmark

Revision ID: 0a629d99201a
Revises: 7eb444c590b1
Create Date: 2025-07-02 10:27:07.131519

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a629d99201a"
down_revision: Union[str, None] = "7eb444c590b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # save copy of bookmarkcategory enum
    op.execute("ALTER TYPE bookmarkcategory RENAME TO bookmarkcategory_old")

    # recreate enum (including the updated SimulationCampaign)
    op.execute(
        "CREATE TYPE bookmarkcategory AS ENUM("
        "'ExperimentalBoutonDensity', "
        "'ExperimentalNeuronDensity', "
        "'ExperimentalElectroPhysiology', "
        "'ExperimentalSynapsePerConnection', "
        "'ExperimentalNeuronMorphology', "
        "'SimulationCampaign', "
        "'CircuitEModel', "
        "'CircuitMEModel', "
        "'SingleNeuronSynaptome', "
        "'SingleNeuronSimulation', "
        "'SynaptomeSimulation'"
        ")"
    )

    # update the table column to use the new enum type with value mapping
    op.execute(
        "ALTER TABLE bookmark ALTER COLUMN category TYPE bookmarkcategory USING "
        "CASE WHEN category::text = 'SimulationCampaigns' THEN 'SimulationCampaign'::bookmarkcategory "
        "ELSE category::text::bookmarkcategory END"
    )

    # drop copy of enum
    op.execute("DROP TYPE bookmarkcategory_old")


def downgrade() -> None:
    # update any existing records from 'SimulationCampaign' back to 'SimulationCampaigns'
    op.execute(
        "UPDATE bookmark SET category = 'SimulationCampaigns' WHERE category = 'SimulationCampaign'"
    )

    # save copy of bookmarkcategory enum
    op.execute("ALTER TYPE bookmarkcategory RENAME TO bookmarkcategory_old")

    # recreate enum (without the new SimulationCampaign)
    op.execute(
        "CREATE TYPE bookmarkcategory AS ENUM("
        "'ExperimentalBoutonDensity', "
        "'ExperimentalNeuronDensity', "
        "'ExperimentalElectroPhysiology', "
        "'ExperimentalSynapsePerConnection', "
        "'ExperimentalNeuronMorphology', "
        "'SimulationCampaigns', "
        "'CircuitEModel', "
        "'CircuitMEModel', "
        "'SingleNeuronSynaptome', "
        "'SingleNeuronSimulation', "
        "'SynaptomeSimulation'"
        ")"
    )

    # update the table column to use the old enum type
    op.execute(
        "ALTER TABLE bookmark ALTER COLUMN category TYPE bookmarkcategory USING "
        "category::text::bookmarkcategory"
    )

    # drop copy of enum
    op.execute("DROP TYPE bookmarkcategory_old")
