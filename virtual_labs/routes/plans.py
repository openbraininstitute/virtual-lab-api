from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.domain.labs import (
    AllPlans,
    LabResponse,
    PlanDomain,
)
from virtual_labs.usecases.plans.all_plans import all_plans

router = APIRouter(prefix="/plans", tags=["Plans Endpoints"])


@router.get("", response_model=LabResponse[AllPlans])
def get_all_plans(
    db: Session = Depends(default_session_factory),
) -> LabResponse[AllPlans]:
    plans = AllPlans(
        all_plans=[PlanDomain.model_validate(plan) for plan in all_plans(db)]
    )

    return LabResponse[AllPlans](message="All plans", data=plans)
