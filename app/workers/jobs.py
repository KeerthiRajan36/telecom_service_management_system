import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.network import NetworkEquipment, Tower
from app.models.notification import Notification
from app.models.plan import ServicePlan
from app.models.sim import SimCard
from app.models.subscription import Subscription, SubscriptionHistory
from app.models.enums import NotificationType, SimStatus, SubscriptionStatus
from app.services import notification_service, sla_service, usage_service
from app.models.ticket import Ticket
from app.utils.audit_logger import record_audit

logger = logging.getLogger("telecom.jobs")

USAGE_THRESHOLDS = (80, 100)


def _already_sent(db: Session, ntype: NotificationType, customer_id: str, text: str, since: datetime) -> bool:
    return (
        db.query(Notification.id)
        .filter(
            Notification.notification_type == ntype,
            Notification.recipient_customer_id == customer_id,
            Notification.message.contains(text),
            Notification.created_at >= since,
        )
        .first()
        is not None
    )


def process_subscription_expiries(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    renewed = expired = 0
    due = db.query(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.end_date < now).all()
    for sub in due:
        plan = db.get(ServicePlan, sub.plan_id)
        if sub.auto_renew:
            new_end = sub.end_date + timedelta(days=plan.validity_days)
            if new_end <= now:  # job was down for a long time; don't create an already-expired cycle
                new_end = now + timedelta(days=plan.validity_days)
            sub.end_date = new_end
            db.add(SubscriptionHistory(subscription_id=sub.id, action="auto_renewed", to_plan_id=plan.id))
            record_audit(db, user_id=None, action="AUTO_RENEW", entity="Subscription", entity_id=sub.id,
                         new_value={"new_end_date": new_end.isoformat()}, commit=False)
            renewed += 1
        else:
            sub.status = SubscriptionStatus.EXPIRED
            db.add(SubscriptionHistory(subscription_id=sub.id, action="expired", from_plan_id=plan.id))
            record_audit(db, user_id=None, action="EXPIRE", entity="Subscription", entity_id=sub.id, commit=False)
            expired += 1
    db.commit()
    return {"renewed": renewed, "expired": expired}


def scan_plan_expiries(db: Session, within_days: int = 3) -> int:
    now = datetime.now(timezone.utc)
    sent = 0
    subs = (
        db.query(Subscription)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE, Subscription.auto_renew.is_(False),
                Subscription.end_date >= now, Subscription.end_date <= now + timedelta(days=within_days))
        .all()
    )
    for sub in subs:
        plan = db.get(ServicePlan, sub.plan_id)
        if _already_sent(db, NotificationType.PLAN_EXPIRY, sub.customer_id, f"'{plan.name}'", now - timedelta(days=1)):
            continue
        days_left = max((sub.end_date - now).days, 0)
        notification_service.notify_plan_expiry(sub.customer_id, plan.name, days_left, db=db)
        sent += 1
    return sent


def scan_maintenance_schedules(db: Session, within_days: int = 2) -> int:
    today = date.today()
    sent = 0
    equipment = (
        db.query(NetworkEquipment)
        .filter(NetworkEquipment.maintenance_schedule.isnot(None),
                NetworkEquipment.maintenance_schedule >= today,
                NetworkEquipment.maintenance_schedule <= today + timedelta(days=within_days))
        .all()
    )
    for eq in equipment:
        tower = db.get(Tower, eq.tower_id)
        when = eq.maintenance_schedule.isoformat()
        customer_ids = sorted({
            s.customer_id for s in db.query(SimCard).filter(
                SimCard.serving_tower_id == tower.id, SimCard.status == SimStatus.ACTIVE, SimCard.customer_id.isnot(None))
        })
        marker = f"tower {tower.code} on {when}"
        fresh = [c for c in customer_ids if not _already_sent(db, NotificationType.MAINTENANCE_SCHEDULE, c, marker, datetime.min.replace(tzinfo=timezone.utc))]
        if fresh:
            notification_service.notify_maintenance_schedule(tower.code, when, fresh, db=db)
            sent += len(fresh)
    return sent


def scan_sla_breaches(db: Session) -> int:
    flagged = 0
    for tracking in sla_service.get_breached_tickets(db):
        if tracking.breached:
            continue
        tracking.breached = True
        ticket = db.get(Ticket, tracking.ticket_id)
        db.commit()
        if ticket:
            notification_service.notify_sla_breach(ticket.ticket_code, ticket.customer_id, db=db)
        flagged += 1
    return flagged


def check_usage_thresholds(db: Session, subscription_id: str) -> int:
    sub = db.get(Subscription, subscription_id)
    if not sub or sub.status != SubscriptionStatus.ACTIVE:
        return 0
    plan = db.get(ServicePlan, sub.plan_id)
    today = date.today()
    period_start = max(sub.start_date.date(), today - timedelta(days=plan.validity_days - 1))
    summary = usage_service.get_subscription_usage_summary(db, sub.id, period_start, today)
    cycle_start = datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)

    sent = 0
    for label, percent in (("data", summary.data_usage_percent), ("voice", summary.voice_usage_percent), ("sms", summary.sms_usage_percent)):
        if percent is None:
            continue
        bucket = max((t for t in USAGE_THRESHOLDS if percent >= t), default=None)
        if bucket is None:
            continue
        text = f"used {bucket}% of your {label} quota"
        if _already_sent(db, NotificationType.USAGE_THRESHOLD, sub.customer_id, text, cycle_start):
            continue
        notification_service.notify_usage_threshold(sub.customer_id, label, bucket, db=db)
        sent += 1
    return sent


def check_usage_thresholds_background(subscription_id: str) -> None:
    with SessionLocal() as db:
        try:
            check_usage_thresholds(db, subscription_id)
        except Exception:  # never let an alerting failure surface to the request that triggered it
            logger.exception("usage threshold check failed for %s", subscription_id)


def run_all_jobs(db: Session) -> dict:
    return {
        "subscriptions": process_subscription_expiries(db),
        "plan_expiry_notifications": scan_plan_expiries(db),
        "maintenance_notifications": scan_maintenance_schedules(db),
        "sla_breaches_flagged": scan_sla_breaches(db),
    }
