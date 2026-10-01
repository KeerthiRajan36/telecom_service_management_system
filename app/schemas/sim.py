from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SimType, SimStatus
from app.schemas.common import ORMModel


class SimCreate(BaseModel):
    sim_number: str
    sim_type: SimType = SimType.PHYSICAL


class SimAssignCustomer(BaseModel):
    customer_id: str


class SimAssignPlan(BaseModel):
    plan_id: str


class SimStatusUpdate(BaseModel):
    status: SimStatus


class SimAssignTower(BaseModel):
    tower_id: str


class SimReplaceRequest(BaseModel):
    new_sim_number: str
    new_sim_type: SimType = SimType.PHYSICAL
    reason: str | None = None


class SimOut(ORMModel):
    id: str
    sim_number: str
    sim_type: SimType
    status: SimStatus
    activation_date: datetime | None
    customer_id: str | None
    current_plan_id: str | None
    serving_tower_id: str | None


class SimReplacementOut(ORMModel):
    id: str
    old_sim_id: str
    new_sim_id: str
    customer_id: str
    reason: str | None
    created_at: datetime
