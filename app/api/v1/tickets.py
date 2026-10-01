from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, require_support_staff, RoleChecker
from app.db.session import get_db
from app.models.user import User
from app.models.ticket import Ticket
from app.models.enums import TicketStatus, TicketPriority, UserRole, AssignmentTargetType
from app.schemas.ticket import (
    TicketCreate, TicketAssignAgent, TicketAssignTechnician, TicketStatusUpdate,
    TicketPriorityUpdate, TicketEscalate, CommentCreate, CommentOut, TicketOut, TicketHistoryOut,
)
from app.schemas.technician import AssignmentCreate
from app.schemas.common import PaginatedResponse
from app.services import ticket_service, technician_service, notification_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/tickets", tags=["Support Tickets"])

require_dispatcher = RoleChecker([UserRole.SUPER_ADMIN, UserRole.OPS_MANAGER, UserRole.SUPPORT_AGENT, UserRole.NETWORK_ENGINEER])


def _assert_ticket_access(user: User, ticket: Ticket):
    """Customers may only see their own tickets."""
    if user.role == UserRole.CUSTOMER and user.customer_id != ticket.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own tickets")


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Customers can raise tickets for themselves; staff can raise them on behalf of any customer."""
    if current_user.role == UserRole.CUSTOMER:
        if not current_user.customer_id or current_user.customer_id != payload.customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers can only create tickets for their own account")
    return ticket_service.create_ticket(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[TicketOut])
def list_tickets(
    ticket_status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    customer_id: str | None = None,
    assigned_agent_id: str | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.CUSTOMER:
        customer_id = current_user.customer_id  # force-scope customers to their own tickets
        if not customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No customer profile linked to this account")
    query = ticket_service.query_tickets(db, ticket_status, priority, customer_id, assigned_agent_id)
    return paginate(query, params, TicketOut, Ticket, search_fields=["ticket_code", "subject", "description"])


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = ticket_service.get_ticket(db, ticket_id)
    _assert_ticket_access(current_user, ticket)
    return ticket


@router.post("/{ticket_id}/assign-agent", response_model=TicketOut)
def assign_agent(
    ticket_id: str,
    payload: TicketAssignAgent,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_dispatcher),
    db: Session = Depends(get_db),
):
    ticket = ticket_service.assign_agent(db, current_user.id, ticket_id, payload.agent_id)
    background_tasks.add_task(
        notification_service.notify_ticket_assignment, ticket.ticket_code, "a support agent",
        None, payload.agent_id,
    )
    return ticket


@router.post("/{ticket_id}/assign-technician", response_model=TicketOut)
def assign_technician(
    ticket_id: str,
    payload: TicketAssignTechnician,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_dispatcher),
    db: Session = Depends(get_db),
):
    ticket_service.get_ticket(db, ticket_id)  # 404 early
    technician_service.assign_technician(
        db, current_user.id,
        AssignmentCreate(technician_id=payload.technician_id, target_type=AssignmentTargetType.TICKET, target_id=ticket_id),
    )
    ticket = ticket_service.get_ticket(db, ticket_id)
    background_tasks.add_task(
        notification_service.notify_ticket_assignment, ticket.ticket_code, "a field technician", ticket.customer_id, None,
    )
    return ticket


@router.patch("/{ticket_id}/priority", response_model=TicketOut)
def set_priority(ticket_id: str, payload: TicketPriorityUpdate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return ticket_service.set_priority(db, current_user.id, ticket_id, payload.priority)


@router.post("/{ticket_id}/escalate", response_model=TicketOut)
def escalate(ticket_id: str, payload: TicketEscalate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return ticket_service.escalate_ticket(db, current_user.id, ticket_id, payload.reason)


@router.patch("/{ticket_id}/status", response_model=TicketOut)
def update_status(
    ticket_id: str,
    payload: TicketStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    ticket = ticket_service.update_status(db, current_user.id, ticket_id, payload.status, payload.resolution_notes)
    # If the ticket was resolved after its SLA deadline, raise an SLA breach notification.
    if payload.status == TicketStatus.RESOLVED:
        from app.models.sla import SLATracking
        tracking = db.query(SLATracking).filter(SLATracking.ticket_id == ticket.id).first()
        if tracking and tracking.breached:
            background_tasks.add_task(notification_service.notify_sla_breach, ticket.ticket_code, ticket.customer_id)
    return ticket


@router.post("/{ticket_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(ticket_id: str, payload: CommentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = ticket_service.get_ticket(db, ticket_id)
    _assert_ticket_access(current_user, ticket)
    if current_user.role == UserRole.CUSTOMER and payload.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers cannot post internal comments")
    return ticket_service.add_comment(db, current_user.id, ticket_id, payload)


@router.get("/{ticket_id}/comments", response_model=list[CommentOut])
def get_comments(ticket_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = ticket_service.get_ticket(db, ticket_id)
    _assert_ticket_access(current_user, ticket)
    include_internal = current_user.role != UserRole.CUSTOMER
    return ticket_service.get_comments(db, ticket_id, include_internal)


@router.get("/{ticket_id}/history", response_model=list[TicketHistoryOut])
def get_history(ticket_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return ticket_service.get_history(db, ticket_id)
