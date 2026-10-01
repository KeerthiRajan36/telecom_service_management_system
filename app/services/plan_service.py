from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.plan import ServicePlan
from app.models.enums import PlanStatus, PlanType, PlanCategory
from app.schemas.plan import PlanCreate, PlanUpdate
from app.utils.audit_logger import record_audit


def create_plan(db: Session, actor_id: str | None, payload: PlanCreate) -> ServicePlan:
    if db.query(ServicePlan).filter(ServicePlan.code == payload.code).first():
        raise AppError("A plan with this code already exists", 409, "PLAN_EXISTS")
    plan = ServicePlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="ServicePlan", entity_id=plan.id, new_value=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(plan)
    return plan


def get_plan(db: Session, plan_id: str) -> ServicePlan:
    plan = db.get(ServicePlan, plan_id)
    if not plan:
        raise NotFoundError("Plan not found")
    return plan


def update_plan(db: Session, actor_id: str | None, plan_id: str, payload: PlanUpdate) -> ServicePlan:
    plan = get_plan(db, plan_id)
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(plan, k) for k in data}
    for field, value in data.items():
        setattr(plan, field, value)
    record_audit(db, user_id=actor_id, action="UPDATE", entity="ServicePlan", entity_id=plan.id, previous_value=before, new_value=data)
    db.commit()
    db.refresh(plan)
    return plan


def set_plan_status(db: Session, actor_id: str | None, plan_id: str, status: PlanStatus) -> ServicePlan:
    plan = get_plan(db, plan_id)
    before = plan.status.value
    plan.status = status
    record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="ServicePlan", entity_id=plan.id, previous_value={"status": before}, new_value={"status": status.value})
    db.commit()
    db.refresh(plan)
    return plan


def query_plans(
    db: Session,
    plan_type: PlanType | None = None,
    category: PlanCategory | None = None,
    status: PlanStatus | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
):
    query = db.query(ServicePlan)
    if plan_type:
        query = query.filter(ServicePlan.plan_type == plan_type)
    if category:
        query = query.filter(ServicePlan.category == category)
    if status:
        query = query.filter(ServicePlan.status == status)
    if min_price is not None:
        query = query.filter(ServicePlan.price >= min_price)
    if max_price is not None:
        query = query.filter(ServicePlan.price <= max_price)
    return query


def compare_plans(db: Session, plan_ids: list[str]) -> list[ServicePlan]:
    plans = db.query(ServicePlan).filter(ServicePlan.id.in_(plan_ids)).all()
    found_ids = {p.id for p in plans}
    missing = set(plan_ids) - found_ids
    if missing:
        raise NotFoundError(f"Plan(s) not found: {', '.join(missing)}")
    # Preserve requested order for a stable comparison table
    order = {pid: i for i, pid in enumerate(plan_ids)}
    plans.sort(key=lambda p: order[p.id])
    return plans
