from typing import Any
from sqlalchemy import Connection, Table
from .plans_data import plans_data


def populate_plans(target: Table, connection: Connection, **kw: Any) -> None:
    """
    Called at the time of creation of "Plan" table, this function populates the table with static data for plans
    """
    connection.execute(
        target.insert(),
        plans_data,
    )
