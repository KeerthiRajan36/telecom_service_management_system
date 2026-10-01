from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, require_support_staff, assert_customer_access
from app.db.session import get_db
from app.models.user import User
from app.models.sim import SimCard
from app.models.enums import SimStatus
from app.schemas.sim import (
    SimCreate, SimOut, SimAssignCustomer, SimAssignPlan, SimAssignTower,
    SimStatusUpdate, SimReplaceRequest, SimReplacementOut,
)
from app.schemas.common import PaginatedResponse
from app.services import sim_service, notification_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/sims", tags=["SIM Cards"])


@router.post("", response_model=SimOut, status_code=status.HTTP_201_CREATED)
def create_sim(payload: SimCreate, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return sim_service.create_sim(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[SimOut])
def list_sims(
    sim_status: SimStatus | None = None,
    customer_id: str | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = sim_service.query_sims(db, sim_status, customer_id)
    return paginate(query, params, SimOut, SimCard, search_fields=["sim_number"])


@router.get("/customers/{customer_id}/replacements", response_model=list[SimReplacementOut])
def replacement_history(customer_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return sim_service.get_replacement_history(db, customer_id)


@router.get("/{sim_id}", response_model=SimOut)
def get_sim(sim_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sim = sim_service.get_sim(db, sim_id)
    assert_customer_access(current_user, sim.customer_id)
    return sim


@router.post("/{sim_id}/assign-customer", response_model=SimOut)
def assign_customer(sim_id: str, payload: SimAssignCustomer, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return sim_service.assign_customer(db, current_user.id, sim_id, payload.customer_id)


@router.post("/{sim_id}/assign-plan", response_model=SimOut)
def assign_plan(sim_id: str, payload: SimAssignPlan, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return sim_service.assign_plan(db, current_user.id, sim_id, payload.plan_id)


@router.post("/{sim_id}/assign-tower", response_model=SimOut)
def assign_tower(sim_id: str, payload: SimAssignTower, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return sim_service.assign_tower(db, current_user.id, sim_id, payload.tower_id)


@router.patch("/{sim_id}/status", response_model=SimOut)
def change_status(
    sim_id: str,
    payload: SimStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_support_staff),
    db: Session = Depends(get_db),
):
    sim = sim_service.change_status(db, current_user.id, sim_id, payload.status)
    if payload.status == SimStatus.SUSPENDED and sim.customer_id:
        background_tasks.add_task(notification_service.notify_sim_suspension, sim.customer_id, sim.sim_number)
    return sim


@router.post("/{sim_id}/replace", response_model=SimOut, status_code=status.HTTP_201_CREATED)
def replace_sim(sim_id: str, payload: SimReplaceRequest, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return sim_service.replace_sim(db, current_user.id, sim_id, payload)
