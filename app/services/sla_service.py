from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.sla import SLARule, SLATracking
from app.models.ticket import Ticket
from app.models.customer import Customer
from app.models.enums import CustomerType
from app.schemas.sla import SLARuleCreate
from app.utils.audit_logger import record_audit


def create_sla_rule(db: Session, actor_id: str | None, payload: SLARuleCreate) -> SLARule:
    existing = (
        db.query(SLARule)
        .filter(
            SLARule.ticket_category == payload.ticket_category,
            SLARule.priority == payload.priority,
            SLARule.customer_type == payload.customer_type,
        )
        .first()
    )
    if existing:
        raise AppError("An SLA rule already exists for this category/priority/customer-type combination", 409, "SLA_RULE_EXISTS")

    rule = SLARule(**payload.model_dump())
    db.add(rule)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="SLARule", entity_id=rule.id, new_value=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(rule)
    return rule


def _find_rule(db: Session, ticket: Ticket, customer_type: CustomerType) -> SLARule | None:
    return (
        db.query(SLARule)
        .filter(
            SLARule.ticket_category == ticket.category,
            SLARule.priority == ticket.priority,
            SLARule.customer_type == customer_type,
        )
        .first()
    )


def start_tracking_for_ticket(db: Session, ticket: Ticket) -> SLATracking | None:
    """Called when a ticket is created. Looks up the matching SLA rule for the
    customer's type + ticket category/priority and starts the SLA clock.
    If no rule matches, no tracking row is created (falls back gracefully)."""
    customer = db.get(Customer, ticket.customer_id)
    customer_type = customer.customer_type if customer else CustomerType.PREPAID

    rule = _find_rule(db, ticket, customer_type)
    if not rule:
        return None

    now = datetime.now(timezone.utc)
    tracking = SLATracking(
        ticket_id=ticket.id,
        sla_rule_id=rule.id,
        sla_start_time=now,
        sla_deadline=now + timedelta(minutes=rule.resolution_time_minutes),
    )
    db.add(tracking)
    db.flush()
    return tracking


def mark_resolved(db: Session, ticket_id: str) -> SLATracking | None:
    tracking = db.query(SLATracking).filter(SLATracking.ticket_id == ticket_id).first()
    if not tracking:
        return None
    now = datetime.now(timezone.utc)
    tracking.resolved_time = now
    if now > tracking.sla_deadline:
        tracking.breached = True
    db.flush()
    return tracking


def get_tracking_for_ticket(db: Session, ticket_id: str) -> SLATracking:
    tracking = db.query(SLATracking).filter(SLATracking.ticket_id == ticket_id).first()
    if not tracking:
        raise NotFoundError("No SLA tracking found for this ticket (no matching SLA rule was defined)")
    return tracking


def get_breached_tickets(db: Session) -> list[SLATracking]:
    now = datetime.now(timezone.utc)
    # Already flagged breached, OR still unresolved but past deadline.
    return (
        db.query(SLATracking)
        .filter(
            SLATracking.resolved_time.is_(None),
            SLATracking.sla_deadline < now,
        )
        .all()
    )


def get_soon_to_breach_tickets(db: Session, within_minutes: int = 60) -> list[SLATracking]:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=within_minutes)
    return (
        db.query(SLATracking)
        .filter(
            SLATracking.resolved_time.is_(None),
            SLATracking.sla_deadline >= now,
            SLATracking.sla_deadline <= horizon,
        )
        .all()
    )


def escalate(db: Session, actor_id: str | None, ticket_id: str) -> SLATracking:
    tracking = get_tracking_for_ticket(db, ticket_id)
    tracking.escalated = True
    record_audit(db, user_id=actor_id, action="SLA_ESCALATE", entity="SLATracking", entity_id=tracking.id)
    db.commit()
    db.refresh(tracking)
    return tracking


def query_rules(db: Session):
    return db.query(SLARule)
