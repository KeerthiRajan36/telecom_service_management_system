from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin_or_ops, require_staff, require_support_staff
from app.db.session import get_db
from app.models.user import User
from app.models.ticket import Ticket
from app.schemas.sla import SLARuleCreate, SLARuleOut, SLATrackingOut
from app.services import sla_service, notification_service

router = APIRouter(prefix="/sla", tags=["SLA Management"])


@router.post("/rules", response_model=SLARuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: SLARuleCreate, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return sla_service.create_sla_rule(db, current_user.id, payload)


@router.get("/rules", response_model=list[SLARuleOut])
def list_rules(current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return sla_service.query_rules(db).all()


@router.get("/tickets/{ticket_id}", response_model=SLATrackingOut)
def ticket_sla(ticket_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return sla_service.get_tracking_for_ticket(db, ticket_id)


@router.get("/breached", response_model=list[SLATrackingOut])
def breached(
    background_tasks: BackgroundTasks,
    notify: bool = False,
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Tickets that are unresolved and past their SLA deadline.
    Pass notify=true to also flag them as breached and raise SLA-breach notifications."""
    rows = sla_service.get_breached_tickets(db)
    if notify:
        for tracking in rows:
            if not tracking.breached:
                tracking.breached = True
                ticket = db.get(Ticket, tracking.ticket_id)
                if ticket:
                    background_tasks.add_task(notification_service.notify_sla_breach, ticket.ticket_code, ticket.customer_id)
        db.commit()
    return rows


@router.get("/soon-to-breach", response_model=list[SLATrackingOut])
def soon_to_breach(within_minutes: int = 60, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return sla_service.get_soon_to_breach_tickets(db, within_minutes)


@router.post("/tickets/{ticket_id}/escalate", response_model=SLATrackingOut)
def escalate(ticket_id: str, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return sla_service.escalate(db, current_user.id, ticket_id)
