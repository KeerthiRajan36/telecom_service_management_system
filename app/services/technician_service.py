from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.technician import Technician, TechnicianAssignment
from app.models.enums import TechnicianAvailability, AssignmentStatus, AssignmentTargetType
from app.schemas.technician import TechnicianCreate, TechnicianUpdate, AssignmentCreate
from app.utils.audit_logger import record_audit


def create_technician(db: Session, actor_id: str | None, payload: TechnicianCreate) -> Technician:
    tech = Technician(**payload.model_dump())
    db.add(tech)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="Technician", entity_id=tech.id, new_value={"full_name": tech.full_name})
    db.commit()
    db.refresh(tech)
    return tech


def get_technician(db: Session, technician_id: str) -> Technician:
    tech = db.get(Technician, technician_id)
    if not tech:
        raise NotFoundError("Technician not found")
    return tech


def update_technician(db: Session, actor_id: str | None, technician_id: str, payload: TechnicianUpdate) -> Technician:
    tech = get_technician(db, technician_id)
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(tech, k) for k in data}
    for field, value in data.items():
        setattr(tech, field, value)
    record_audit(db, user_id=actor_id, action="UPDATE", entity="Technician", entity_id=tech.id, previous_value=before, new_value=data)
    db.commit()
    db.refresh(tech)
    return tech


def query_technicians(db: Session, availability: TechnicianAvailability | None = None, service_area: str | None = None):
    query = db.query(Technician)
    if availability:
        query = query.filter(Technician.availability_status == availability)
    if service_area:
        query = query.filter(Technician.service_area.ilike(f"%{service_area}%"))
    return query


def assign_technician(db: Session, actor_id: str | None, payload: AssignmentCreate) -> TechnicianAssignment:
    tech = get_technician(db, payload.technician_id)
    if tech.availability_status == TechnicianAvailability.OFF_DUTY:
        raise AppError("Technician is off duty and cannot be assigned new work", 409, "TECHNICIAN_UNAVAILABLE")

    assignment = TechnicianAssignment(
        technician_id=tech.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        status=AssignmentStatus.ASSIGNED,
        assigned_at=datetime.now(timezone.utc),
        notes=payload.notes,
    )
    db.add(assignment)
    tech.availability_status = TechnicianAvailability.BUSY

    # Keep the target entity's assigned_technician_id column in sync for tickets.
    if payload.target_type == AssignmentTargetType.TICKET:
        from app.models.ticket import Ticket
        from app.models.enums import TicketStatus

        ticket = db.get(Ticket, payload.target_id)
        if not ticket:
            raise NotFoundError("Ticket not found")
        ticket.assigned_technician_id = tech.id
        if ticket.status == TicketStatus.OPEN:
            ticket.status = TicketStatus.ASSIGNED

    record_audit(db, user_id=actor_id, action="ASSIGN", entity="TechnicianAssignment", entity_id=None, new_value=payload.model_dump())
    db.commit()
    db.refresh(assignment)
    return assignment


def reassign_technician(db: Session, actor_id: str | None, assignment_id: str, new_technician_id: str, notes: str | None = None) -> TechnicianAssignment:
    assignment = db.get(TechnicianAssignment, assignment_id)
    if not assignment:
        raise NotFoundError("Assignment not found")
    new_tech = get_technician(db, new_technician_id)
    if new_tech.availability_status == TechnicianAvailability.OFF_DUTY:
        raise AppError("New technician is off duty", 409, "TECHNICIAN_UNAVAILABLE")

    old_tech = get_technician(db, assignment.technician_id)
    assignment.status = AssignmentStatus.CANCELLED
    db.flush()

    new_assignment = TechnicianAssignment(
        technician_id=new_tech.id,
        target_type=assignment.target_type,
        target_id=assignment.target_id,
        status=AssignmentStatus.ASSIGNED,
        assigned_at=datetime.now(timezone.utc),
        notes=notes or f"Reassigned from technician {old_tech.id}",
    )
    db.add(new_assignment)
    new_tech.availability_status = TechnicianAvailability.BUSY

    # Free up the old technician if they have no other active assignments.
    remaining = (
        db.query(TechnicianAssignment)
        .filter(TechnicianAssignment.technician_id == old_tech.id, TechnicianAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS]))
        .count()
    )
    if remaining == 0:
        old_tech.availability_status = TechnicianAvailability.AVAILABLE

    if assignment.target_type == AssignmentTargetType.TICKET:
        from app.models.ticket import Ticket

        ticket = db.get(Ticket, assignment.target_id)
        if ticket:
            ticket.assigned_technician_id = new_tech.id

    record_audit(db, user_id=actor_id, action="REASSIGN", entity="TechnicianAssignment", entity_id=assignment_id, new_value={"new_technician_id": new_tech.id})
    db.commit()
    db.refresh(new_assignment)
    return new_assignment


def complete_assignment(db: Session, actor_id: str | None, assignment_id: str, notes: str | None = None) -> TechnicianAssignment:
    assignment = db.get(TechnicianAssignment, assignment_id)
    if not assignment:
        raise NotFoundError("Assignment not found")
    assignment.status = AssignmentStatus.COMPLETED
    assignment.completed_at = datetime.now(timezone.utc)
    if notes:
        assignment.notes = notes

    tech = get_technician(db, assignment.technician_id)
    remaining = (
        db.query(TechnicianAssignment)
        .filter(TechnicianAssignment.technician_id == tech.id, TechnicianAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS]))
        .count()
    )
    if remaining == 0:
        tech.availability_status = TechnicianAvailability.AVAILABLE

    record_audit(db, user_id=actor_id, action="COMPLETE", entity="TechnicianAssignment", entity_id=assignment_id)
    db.commit()
    db.refresh(assignment)
    return assignment


def get_workload(db: Session, technician_id: str) -> dict:
    tech = get_technician(db, technician_id)
    pending = db.query(TechnicianAssignment).filter(TechnicianAssignment.technician_id == tech.id, TechnicianAssignment.status == AssignmentStatus.ASSIGNED).count()
    in_progress = db.query(TechnicianAssignment).filter(TechnicianAssignment.technician_id == tech.id, TechnicianAssignment.status == AssignmentStatus.IN_PROGRESS).count()
    completed = db.query(TechnicianAssignment).filter(TechnicianAssignment.technician_id == tech.id, TechnicianAssignment.status == AssignmentStatus.COMPLETED).count()
    return {
        "technician_id": tech.id,
        "full_name": tech.full_name,
        "pending_jobs": pending,
        "in_progress_jobs": in_progress,
        "completed_jobs": completed,
    }


def get_assignments(db: Session, technician_id: str, status: AssignmentStatus | None = None):
    query = db.query(TechnicianAssignment).filter(TechnicianAssignment.technician_id == technician_id)
    if status:
        query = query.filter(TechnicianAssignment.status == status)
    return query.order_by(TechnicianAssignment.assigned_at.desc()).all()
