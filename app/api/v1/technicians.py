from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin_or_ops, require_network_staff, require_staff, RoleChecker
from app.db.session import get_db
from app.models.user import User
from app.models.technician import Technician
from app.models.enums import TechnicianAvailability, AssignmentStatus, UserRole
from app.schemas.technician import (
    TechnicianCreate, TechnicianUpdate, TechnicianOut, AssignmentCreate,
    ReassignRequest, AssignmentOut, TechnicianWorkload,
)
from app.schemas.common import PaginatedResponse
from app.services import technician_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/technicians", tags=["Field Technicians"])

# Dispatching work is allowed for ops managers, admins, network engineers and support agents.
require_dispatcher = RoleChecker([UserRole.SUPER_ADMIN, UserRole.OPS_MANAGER, UserRole.NETWORK_ENGINEER, UserRole.SUPPORT_AGENT])


@router.post("", response_model=TechnicianOut, status_code=status.HTTP_201_CREATED)
def create_technician(payload: TechnicianCreate, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return technician_service.create_technician(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[TechnicianOut])
def list_technicians(
    availability: TechnicianAvailability | None = None,
    service_area: str | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = technician_service.query_technicians(db, availability, service_area)
    return paginate(query, params, TechnicianOut, Technician, search_fields=["full_name", "skills", "service_area"])


# NOTE: static "/assignments" routes are declared before "/{technician_id}" so they aren't shadowed.
@router.post("/assignments", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def assign_technician(payload: AssignmentCreate, current_user: User = Depends(require_dispatcher), db: Session = Depends(get_db)):
    return technician_service.assign_technician(db, current_user.id, payload)


@router.post("/assignments/{assignment_id}/reassign", response_model=AssignmentOut)
def reassign(assignment_id: str, payload: ReassignRequest, current_user: User = Depends(require_dispatcher), db: Session = Depends(get_db)):
    return technician_service.reassign_technician(db, current_user.id, assignment_id, payload.new_technician_id, payload.notes)


@router.post("/assignments/{assignment_id}/complete", response_model=AssignmentOut)
def complete_assignment(assignment_id: str, notes: str | None = None, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return technician_service.complete_assignment(db, current_user.id, assignment_id, notes)


@router.get("/{technician_id}", response_model=TechnicianOut)
def get_technician(technician_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return technician_service.get_technician(db, technician_id)


@router.patch("/{technician_id}", response_model=TechnicianOut)
def update_technician(technician_id: str, payload: TechnicianUpdate, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return technician_service.update_technician(db, current_user.id, technician_id, payload)


@router.get("/{technician_id}/workload", response_model=TechnicianWorkload)
def workload(technician_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return technician_service.get_workload(db, technician_id)


@router.get("/{technician_id}/assignments", response_model=list[AssignmentOut])
def assignments(technician_id: str, assignment_status: AssignmentStatus | None = None, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Use assignment_status=completed for completed jobs, =assigned for pending jobs."""
    return technician_service.get_assignments(db, technician_id, assignment_status)
