from pydantic import UUID4
from sqlalchemy.orm import Session

from virtual_labs.infrastructure.db.models import VirtualLab


class VirtualLabQueryRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def retrieve_lab_by_id(self, virtual_lab_id: UUID4) -> VirtualLab:
        return (
            self.session.query(VirtualLab).filter(VirtualLab.id == virtual_lab_id).one()
        )
