from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import SessionLocal
from app.models.notification import Notification
from app.models.enums import NotificationType


@contextmanager
def _session(db: Session | None):
    if db is not None:
        yield db
        return
    own = SessionLocal()
    try:
        yield own
    finally:
        own.close()


def _create(db: Session, *, notification_type: NotificationType, title: str, message: str,
            user_id: str | None = None, customer_id: str | None = None) -> Notification:
    note = Notification(
        recipient_user_id=user_id,
        recipient_customer_id=customer_id,
        notification_type=notification_type,
        title=title,
        message=message,
    )
    db.add(note)
    db.commit()
    return note


def notify_ticket_assignment(ticket_id: str, assignee_label: str, customer_id: str | None = None,
                             user_id: str | None = None, db: Session | None = None):
    with _session(db) as s:
        _create(s, notification_type=NotificationType.TICKET_ASSIGNMENT, title="Ticket assigned",
                message=f"Ticket {ticket_id} has been assigned to {assignee_label}.",
                customer_id=customer_id, user_id=user_id)


def notify_sla_breach(ticket_id: str, customer_id: str | None = None, db: Session | None = None):
    with _session(db) as s:
        _create(s, notification_type=NotificationType.SLA_BREACH, title="SLA breached",
                message=f"Ticket {ticket_id} has breached its SLA resolution deadline.",
                customer_id=customer_id)


def notify_network_outage(outage_id: str, customer_ids: list[str], db: Session | None = None):
    with _session(db) as s:
        for cid in customer_ids:
            _create(s, notification_type=NotificationType.NETWORK_OUTAGE,
                    title="Network outage affecting your service",
                    message=f"An outage ({outage_id}) may be affecting your network service. We are working on it.",
                    customer_id=cid)


def notify_service_restoration(outage_id: str, customer_ids: list[str], db: Session | None = None):
    with _session(db) as s:
        for cid in customer_ids:
            _create(s, notification_type=NotificationType.SERVICE_RESTORATION, title="Service restored",
                    message=f"Service has been restored following outage {outage_id}.", customer_id=cid)


def notify_plan_expiry(customer_id: str, plan_name: str, days_remaining: int, db: Session | None = None):
    with _session(db) as s:
        _create(s, notification_type=NotificationType.PLAN_EXPIRY, title="Plan expiring soon",
                message=f"Your plan '{plan_name}' expires in {days_remaining} day(s). Renew to avoid interruption.",
                customer_id=customer_id)


def notify_usage_threshold(customer_id: str, usage_type: str, percent_used: float, db: Session | None = None):
    with _session(db) as s:
        _create(s, notification_type=NotificationType.USAGE_THRESHOLD, title=f"{usage_type.title()} usage alert",
                message=f"You have used {percent_used:.0f}% of your {usage_type} quota.", customer_id=customer_id)


def notify_sim_suspension(customer_id: str, sim_number: str, db: Session | None = None):
    with _session(db) as s:
        _create(s, notification_type=NotificationType.SIM_SUSPENSION, title="SIM suspended",
                message=f"Your SIM {sim_number} has been suspended.", customer_id=customer_id)


def notify_maintenance_schedule(tower_code: str, scheduled_date: str, customer_ids: list[str], db: Session | None = None):
    with _session(db) as s:
        for cid in customer_ids:
            _create(s, notification_type=NotificationType.MAINTENANCE_SCHEDULE, title="Scheduled maintenance",
                    message=f"Maintenance is scheduled for tower {tower_code} on {scheduled_date}; brief interruptions may occur.",
                    customer_id=cid)


def list_notifications(db: Session, user_id: str | None = None, customer_id: str | None = None, unread_only: bool = False):
    query = db.query(Notification)
    if user_id:
        query = query.filter(Notification.recipient_user_id == user_id)
    if customer_id:
        query = query.filter(Notification.recipient_customer_id == customer_id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc())


def mark_read(db: Session, notification_id: str) -> Notification:
    note = db.get(Notification, notification_id)
    if not note:
        raise NotFoundError("Notification not found")
    note.is_read = True
    db.commit()
    db.refresh(note)
    return note
