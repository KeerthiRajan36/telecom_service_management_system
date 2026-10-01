from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.ticket import Ticket, TicketComment, TicketHistory
from app.models.customer import Customer
from app.models.user import User
from app.models.enums import TicketStatus, TicketPriority, UserRole
from app.schemas.ticket import TicketCreate, CommentCreate
from app.utils.codes import gen_ticket_code
from app.utils.audit_logger import record_audit
from app.services import sla_service, customer_service

_ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    TicketStatus.ASSIGNED: {TicketStatus.IN_PROGRESS, TicketStatus.WAITING_FOR_CUSTOMER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.IN_PROGRESS: {TicketStatus.WAITING_FOR_CUSTOMER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.WAITING_FOR_CUSTOMER: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
    TicketStatus.CLOSED: set(),
}


def _log_history(db: Session, ticket_id: str, action: str, actor_id: str | None, from_value=None, to_value=None):
    db.add(TicketHistory(ticket_id=ticket_id, action=action, actor_id=actor_id, from_value=str(from_value) if from_value is not None else None, to_value=str(to_value) if to_value is not None else None))


def create_ticket(db: Session, actor_id: str | None, payload: TicketCreate) -> Ticket:
    customer_service.get_customer(db, payload.customer_id)  # 404 if missing/deleted

    ticket = Ticket(
        ticket_code=gen_ticket_code(),
        customer_id=payload.customer_id,
        category=payload.category,
        subject=payload.subject,
        description=payload.description,
        priority=payload.priority,
        related_sim_id=payload.related_sim_id,
        related_device_id=payload.related_device_id,
        status=TicketStatus.OPEN,
    )
    db.add(ticket)
    db.flush()

    sla_service.start_tracking_for_ticket(db, ticket)
    _log_history(db, ticket.id, "created", actor_id, to_value=ticket.status.value)
    record_audit(db, user_id=actor_id, action="CREATE", entity="Ticket", entity_id=ticket.id, new_value={"category": ticket.category.value, "priority": ticket.priority.value})
    db.commit()
    db.refresh(ticket)
    return ticket


def get_ticket(db: Session, ticket_id: str) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise NotFoundError("Ticket not found")
    return ticket


def assign_agent(db: Session, actor_id: str | None, ticket_id: str, agent_id: str) -> Ticket:
    ticket = get_ticket(db, ticket_id)
    agent = db.get(User, agent_id)
    if not agent:
        raise NotFoundError("Agent not found")
    if agent.role not in (UserRole.SUPPORT_AGENT, UserRole.OPS_MANAGER, UserRole.SUPER_ADMIN):
        raise AppError("Selected user is not a support agent", 409, "INVALID_AGENT")

    before = ticket.assigned_agent_id
    ticket.assigned_agent_id = agent.id
    if ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.ASSIGNED
    _log_history(db, ticket.id, "agent_assigned", actor_id, before, agent.id)
    record_audit(db, user_id=actor_id, action="ASSIGN_AGENT", entity="Ticket", entity_id=ticket.id, new_value={"agent_id": agent.id})
    db.commit()
    db.refresh(ticket)
    return ticket


def set_priority(db: Session, actor_id: str | None, ticket_id: str, priority: TicketPriority) -> Ticket:
    ticket = get_ticket(db, ticket_id)
    before = ticket.priority.value
    ticket.priority = priority
    _log_history(db, ticket.id, "priority_changed", actor_id, before, priority.value)
    record_audit(db, user_id=actor_id, action="PRIORITY_CHANGE", entity="Ticket", entity_id=ticket.id, previous_value={"priority": before}, new_value={"priority": priority.value})
    db.commit()
    db.refresh(ticket)
    return ticket


def escalate_ticket(db: Session, actor_id: str | None, ticket_id: str, reason: str | None = None) -> Ticket:
    ticket = get_ticket(db, ticket_id)
    ticket.escalated = True
    _log_history(db, ticket.id, "escalated", actor_id, to_value=reason)

    tracking = db.query(sla_service.SLATracking).filter(sla_service.SLATracking.ticket_id == ticket_id).first()
    if tracking:
        tracking.escalated = True

    record_audit(db, user_id=actor_id, action="ESCALATE", entity="Ticket", entity_id=ticket.id, new_value={"reason": reason})
    db.commit()
    db.refresh(ticket)
    return ticket


def update_status(db: Session, actor_id: str | None, ticket_id: str, new_status: TicketStatus, resolution_notes: str | None = None) -> Ticket:
    ticket = get_ticket(db, ticket_id)
    if new_status == ticket.status:
        raise AppError(f"Ticket is already {ticket.status.value}", 409, "ALREADY_IN_STATE")
    allowed = _ALLOWED_TRANSITIONS.get(ticket.status, set())
    if new_status not in allowed:
        raise AppError(f"Cannot transition ticket from {ticket.status.value} to {new_status.value}", 409, "INVALID_TRANSITION")

    before = ticket.status.value
    ticket.status = new_status
    now = datetime.now(timezone.utc)

    if new_status == TicketStatus.RESOLVED:
        ticket.resolved_at = now
        if resolution_notes:
            ticket.resolution_notes = resolution_notes
        sla_service.mark_resolved(db, ticket.id)
    elif new_status == TicketStatus.CLOSED:
        ticket.closed_at = now

    _log_history(db, ticket.id, "status_changed", actor_id, before, new_status.value)
    record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="Ticket", entity_id=ticket.id, previous_value={"status": before}, new_value={"status": new_status.value})
    db.commit()
    db.refresh(ticket)
    return ticket


def add_comment(db: Session, actor_id: str, ticket_id: str, payload: CommentCreate) -> TicketComment:
    ticket = get_ticket(db, ticket_id)
    comment = TicketComment(ticket_id=ticket.id, author_id=actor_id, is_internal=payload.is_internal, body=payload.body)
    db.add(comment)
    _log_history(db, ticket.id, "comment_added", actor_id)
    db.commit()
    db.refresh(comment)
    return comment


def get_comments(db: Session, ticket_id: str, include_internal: bool = True) -> list[TicketComment]:
    query = db.query(TicketComment).filter(TicketComment.ticket_id == ticket_id)
    if not include_internal:
        query = query.filter(TicketComment.is_internal.is_(False))
    return query.order_by(TicketComment.created_at).all()


def get_history(db: Session, ticket_id: str) -> list[TicketHistory]:
    get_ticket(db, ticket_id)
    return db.query(TicketHistory).filter(TicketHistory.ticket_id == ticket_id).order_by(TicketHistory.created_at.desc()).all()


def query_tickets(db: Session, status: TicketStatus | None = None, priority: TicketPriority | None = None, customer_id: str | None = None, assigned_agent_id: str | None = None):
    query = db.query(Ticket)
    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if customer_id:
        query = query.filter(Ticket.customer_id == customer_id)
    if assigned_agent_id:
        query = query.filter(Ticket.assigned_agent_id == assigned_agent_id)
    return query
