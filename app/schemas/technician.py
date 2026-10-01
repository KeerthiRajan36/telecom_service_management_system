from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TechnicianAvailability, AssignmentTargetType, AssignmentStatus
from app.schemas.common import ORMModel


class TechnicianCreate(BaseModel):
    full_name: str
    phone: str
    skills: str = ""
    service_area: str
    latitude: float | None = None
    longitude: float | None = None
    user_id: str | None = None


class TechnicianUpdate(BaseModel):
    skills: str | None = None
    service_area: str | None = None
    availability_status: TechnicianAvailability | None = None
    latitude: float | None = None
    longitude: float | None = None


class TechnicianOut(ORMModel):
    id: str
    full_name: str
    phone: str
    skills: str
    service_area: str
    availability_status: TechnicianAvailability


class AssignmentCreate(BaseModel):
    technician_id: str
    target_type: AssignmentTargetType
    target_id: str
    notes: str | None = None


class ReassignRequest(BaseModel):
    new_technician_id: str
    notes: str | None = None


class AssignmentOut(ORMModel):
    id: str
    technician_id: str
    target_type: AssignmentTargetType
    target_id: str
    status: AssignmentStatus
    assigned_at: datetime
    completed_at: datetime | None
    notes: str | None


class TechnicianWorkload(BaseModel):
    technician_id: str
    full_name: str
    pending_jobs: int
    completed_jobs: int
    in_progress_jobs: int
