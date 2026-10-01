from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.subscription import Subscription, SubscriptionHistory
from app.models.sim import SimCard
from app.models.plan import ServicePlan
from app.models.customer import Customer
from app.models.enums import SubscriptionStatus, SimStatus, PlanStatus
from app.services import customer_service
from app.schemas.subscription import SubscriptionCreate
from app.utils.audit_logger import record_audit

_ALLOWED_TRANSITIONS: dict[SubscriptionStatus, set[SubscriptionStatus]] = {
    SubscriptionStatus.PENDING: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED},
    SubscriptionStatus.ACTIVE: {SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED},
    SubscriptionStatus.SUSPENDED: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED},
    SubscriptionStatus.EXPIRED: {SubscriptionStatus.ACTIVE},
    SubscriptionStatus.CANCELLED: set(),
}


def _log_history(db: Session, subscription_id: str, action: str, from_plan_id: str | None = None, to_plan_id: str | None = None, notes: str | None = None):
    db.add(SubscriptionHistory(subscription_id=subscription_id, action=action, from_plan_id=from_plan_id, to_plan_id=to_plan_id, notes=notes))


def create_subscription(db: Session, actor_id: str | None, payload: SubscriptionCreate) -> Subscription:
    customer = customer_service.get_customer(db, payload.customer_id)  # 404 if missing or soft-deleted
    if not customer.is_active:
        raise AppError("Customer account is deactivated", 409, "CUSTOMER_INACTIVE")
    sim = db.get(SimCard, payload.sim_id)
    if not sim:
        raise NotFoundError("SIM not found")
    if sim.status not in (SimStatus.AVAILABLE, SimStatus.ACTIVE):
        raise AppError(f"SIM is {sim.status.value} and cannot be subscribed", 409, "INVALID_SIM_STATE")
    if sim.customer_id and sim.customer_id != customer.id:
        raise AppError("SIM belongs to a different customer", 409, "SIM_OWNERSHIP_MISMATCH")
    plan = db.get(ServicePlan, payload.plan_id)
    if not plan:
        raise NotFoundError("Plan not found")
    if plan.status != PlanStatus.ACTIVE:
        raise AppError("Plan is not active and cannot be subscribed to", 409, "PLAN_INACTIVE")

    existing_active = (
        db.query(Subscription)
        .filter(Subscription.sim_id == sim.id, Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING]))
        .first()
    )
    if existing_active:
        raise AppError("This SIM already has an active/pending subscription", 409, "SUBSCRIPTION_EXISTS")

    now = datetime.now(timezone.utc)
    sub = Subscription(
        customer_id=customer.id,
        sim_id=sim.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        start_date=now,
        end_date=now + timedelta(days=plan.validity_days),
        auto_renew=payload.auto_renew,
    )
    db.add(sub)
    db.flush()

    sim.current_plan_id = plan.id
    if sim.customer_id is None:
        sim.customer_id = customer.id
    if sim.status == SimStatus.AVAILABLE:
        sim.status = SimStatus.ACTIVE
        sim.activation_date = now

    _log_history(db, sub.id, "created", to_plan_id=plan.id)
    record_audit(db, user_id=actor_id, action="CREATE", entity="Subscription", entity_id=sub.id, new_value={"plan_id": plan.id})
    db.commit()
    db.refresh(sub)
    return sub


def get_subscription(db: Session, subscription_id: str) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise NotFoundError("Subscription not found")
    return sub


def _change_status(db: Session, actor_id: str | None, sub: Subscription, new_status: SubscriptionStatus, action_label: str, notes: str | None = None):
    if new_status == sub.status:
        raise AppError(f"Subscription is already {sub.status.value}", 409, "ALREADY_IN_STATE")
    if new_status not in _ALLOWED_TRANSITIONS.get(sub.status, set()):
        raise AppError(f"Cannot transition subscription from {sub.status.value} to {new_status.value}", 409, "INVALID_TRANSITION")
    before = sub.status.value
    sub.status = new_status
    _log_history(db, sub.id, action_label, notes=notes)
    record_audit(db, user_id=actor_id, action=action_label.upper(), entity="Subscription", entity_id=sub.id, previous_value={"status": before}, new_value={"status": new_status.value})


def suspend_subscription(db: Session, actor_id: str | None, subscription_id: str, notes: str | None = None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _change_status(db, actor_id, sub, SubscriptionStatus.SUSPENDED, "suspended", notes)
    db.commit()
    db.refresh(sub)
    return sub


def reactivate_subscription(db: Session, actor_id: str | None, subscription_id: str, notes: str | None = None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _change_status(db, actor_id, sub, SubscriptionStatus.ACTIVE, "reactivated", notes)
    db.commit()
    db.refresh(sub)
    return sub


def cancel_subscription(db: Session, actor_id: str | None, subscription_id: str, notes: str | None = None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    _change_status(db, actor_id, sub, SubscriptionStatus.CANCELLED, "cancelled", notes)
    sim = db.get(SimCard, sub.sim_id)
    if sim and sim.status == SimStatus.ACTIVE:
        sim.status = SimStatus.SUSPENDED
    db.commit()
    db.refresh(sub)
    return sub


def renew_subscription(db: Session, actor_id: str | None, subscription_id: str) -> Subscription:
    sub = get_subscription(db, subscription_id)
    plan = db.get(ServicePlan, sub.plan_id)
    if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
        raise AppError(f"Cannot renew a subscription in status {sub.status.value}", 409, "INVALID_TRANSITION")

    base = sub.end_date if sub.end_date and sub.end_date > datetime.now(timezone.utc) else datetime.now(timezone.utc)
    sub.end_date = base + timedelta(days=plan.validity_days)
    sub.status = SubscriptionStatus.ACTIVE
    _log_history(db, sub.id, "renewed", to_plan_id=plan.id)
    record_audit(db, user_id=actor_id, action="RENEW", entity="Subscription", entity_id=sub.id, new_value={"new_end_date": sub.end_date.isoformat()})
    db.commit()
    db.refresh(sub)
    return sub


def change_plan(db: Session, actor_id: str | None, subscription_id: str, new_plan_id: str, notes: str | None = None) -> Subscription:
    sub = get_subscription(db, subscription_id)
    if sub.status not in (SubscriptionStatus.ACTIVE,):
        raise AppError("Subscription must be ACTIVE to change plans", 409, "INVALID_TRANSITION")

    old_plan = db.get(ServicePlan, sub.plan_id)
    new_plan = db.get(ServicePlan, new_plan_id)
    if not new_plan:
        raise NotFoundError("Target plan not found")
    if new_plan.status != PlanStatus.ACTIVE:
        raise AppError("Target plan is not active", 409, "PLAN_INACTIVE")
    if new_plan.id == old_plan.id:
        raise AppError("Customer is already on this plan", 409, "SAME_PLAN")

    action_label = "upgraded" if new_plan.price > old_plan.price else "downgraded"
    sub.plan_id = new_plan.id

    sim = db.get(SimCard, sub.sim_id)
    if sim:
        sim.current_plan_id = new_plan.id

    _log_history(db, sub.id, action_label, from_plan_id=old_plan.id, to_plan_id=new_plan.id, notes=notes)
    record_audit(db, user_id=actor_id, action=action_label.upper(), entity="Subscription", entity_id=sub.id, previous_value={"plan_id": old_plan.id}, new_value={"plan_id": new_plan.id})
    db.commit()
    db.refresh(sub)
    return sub


def get_history(db: Session, subscription_id: str) -> list[SubscriptionHistory]:
    get_subscription(db, subscription_id)
    return db.query(SubscriptionHistory).filter(SubscriptionHistory.subscription_id == subscription_id).order_by(SubscriptionHistory.created_at.desc()).all()


def query_subscriptions(db: Session, customer_id: str | None = None, status: SubscriptionStatus | None = None):
    query = db.query(Subscription)
    if customer_id:
        query = query.filter(Subscription.customer_id == customer_id)
    if status:
        query = query.filter(Subscription.status == status)
    return query
