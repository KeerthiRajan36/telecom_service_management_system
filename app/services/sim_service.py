from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.sim import SimCard, SimReplacement
from app.models.customer import Customer
from app.models.plan import ServicePlan
from app.models.enums import SimStatus
from app.schemas.sim import SimCreate, SimReplaceRequest
from app.utils.audit_logger import record_audit
from app.services import customer_service

# Valid status transitions -> keeps SIM lifecycle sane instead of allowing any-to-any jumps.
_ALLOWED_TRANSITIONS: dict[SimStatus, set[SimStatus]] = {
    SimStatus.AVAILABLE: {SimStatus.ACTIVE, SimStatus.BLOCKED},
    SimStatus.ACTIVE: {SimStatus.SUSPENDED, SimStatus.LOST, SimStatus.BLOCKED, SimStatus.DEACTIVATED},
    SimStatus.SUSPENDED: {SimStatus.ACTIVE, SimStatus.DEACTIVATED, SimStatus.BLOCKED},
    SimStatus.LOST: {SimStatus.BLOCKED, SimStatus.DEACTIVATED},
    SimStatus.BLOCKED: {SimStatus.DEACTIVATED},
    SimStatus.DEACTIVATED: set(),
}


def create_sim(db: Session, actor_id: str | None, payload: SimCreate) -> SimCard:
    if db.query(SimCard).filter(SimCard.sim_number == payload.sim_number).first():
        raise AppError("A SIM with this number already exists", 409, "SIM_EXISTS")
    sim = SimCard(sim_number=payload.sim_number, sim_type=payload.sim_type, status=SimStatus.AVAILABLE)
    db.add(sim)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="SimCard", entity_id=sim.id, new_value={"sim_number": sim.sim_number})
    db.commit()
    db.refresh(sim)
    return sim


def get_sim(db: Session, sim_id: str) -> SimCard:
    sim = db.get(SimCard, sim_id)
    if not sim:
        raise NotFoundError("SIM not found")
    return sim


def assign_customer(db: Session, actor_id: str | None, sim_id: str, customer_id: str) -> SimCard:
    sim = get_sim(db, sim_id)
    customer = customer_service.get_customer(db, customer_id)
    if sim.status not in (SimStatus.AVAILABLE,):
        raise AppError(f"SIM must be AVAILABLE to assign a customer (currently {sim.status.value})", 409, "INVALID_SIM_STATE")

    sim.customer_id = customer.id
    record_audit(db, user_id=actor_id, action="ASSIGN_CUSTOMER", entity="SimCard", entity_id=sim.id, new_value={"customer_id": customer.id})
    db.commit()
    db.refresh(sim)
    return sim


def assign_plan(db: Session, actor_id: str | None, sim_id: str, plan_id: str) -> SimCard:
    sim = get_sim(db, sim_id)
    plan = db.get(ServicePlan, plan_id)
    if not plan:
        raise NotFoundError("Plan not found")
    sim.current_plan_id = plan.id
    record_audit(db, user_id=actor_id, action="ASSIGN_PLAN", entity="SimCard", entity_id=sim.id, new_value={"plan_id": plan.id})
    db.commit()
    db.refresh(sim)
    return sim


def assign_tower(db: Session, actor_id: str | None, sim_id: str, tower_id: str) -> SimCard:
    """Sets which tower currently serves this SIM. This mapping is what lets
    outage_service auto-derive which customers are affected by a tower going down."""
    from app.models.network import Tower

    sim = get_sim(db, sim_id)
    tower = db.get(Tower, tower_id)
    if not tower:
        raise NotFoundError("Tower not found")
    sim.serving_tower_id = tower.id
    record_audit(db, user_id=actor_id, action="ASSIGN_TOWER", entity="SimCard", entity_id=sim.id, new_value={"tower_id": tower.id})
    db.commit()
    db.refresh(sim)
    return sim


def change_status(db: Session, actor_id: str | None, sim_id: str, new_status: SimStatus) -> SimCard:
    sim = get_sim(db, sim_id)
    if new_status == sim.status:
        raise AppError(f"SIM is already {sim.status.value}", 409, "ALREADY_IN_STATE")
    allowed = _ALLOWED_TRANSITIONS.get(sim.status, set())
    if new_status not in allowed:
        raise AppError(
            f"Cannot transition SIM from {sim.status.value} to {new_status.value}", 409, "INVALID_TRANSITION"
        )
    before = sim.status.value
    sim.status = new_status
    if new_status == SimStatus.ACTIVE and sim.activation_date is None:
        sim.activation_date = datetime.now(timezone.utc)
    record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="SimCard", entity_id=sim.id, previous_value={"status": before}, new_value={"status": new_status.value})
    db.commit()
    db.refresh(sim)
    return sim


def replace_sim(db: Session, actor_id: str | None, old_sim_id: str, payload: SimReplaceRequest) -> SimCard:
    old_sim = get_sim(db, old_sim_id)
    if not old_sim.customer_id:
        raise AppError("SIM is not assigned to a customer; nothing to replace", 409, "SIM_NOT_ASSIGNED")
    if db.query(SimCard).filter(SimCard.sim_number == payload.new_sim_number).first():
        raise AppError("A SIM with this number already exists", 409, "SIM_EXISTS")

    new_sim = SimCard(
        sim_number=payload.new_sim_number,
        sim_type=payload.new_sim_type,
        status=SimStatus.ACTIVE,
        activation_date=datetime.now(timezone.utc),
        customer_id=old_sim.customer_id,
        current_plan_id=old_sim.current_plan_id,
    )
    db.add(new_sim)
    db.flush()

    old_sim.status = SimStatus.DEACTIVATED
    old_sim.customer_id = None

    db.add(
        SimReplacement(
            old_sim_id=old_sim.id,
            new_sim_id=new_sim.id,
            customer_id=new_sim.customer_id,
            reason=payload.reason,
        )
    )

    record_audit(db, user_id=actor_id, action="REPLACE", entity="SimCard", entity_id=old_sim.id, new_value={"new_sim_id": new_sim.id, "reason": payload.reason})
    db.commit()
    db.refresh(new_sim)
    return new_sim


def get_replacement_history(db: Session, customer_id: str) -> list[SimReplacement]:
    return db.query(SimReplacement).filter(SimReplacement.customer_id == customer_id).order_by(SimReplacement.created_at.desc()).all()


def query_sims(db: Session, status: SimStatus | None = None, customer_id: str | None = None):
    query = db.query(SimCard)
    if status:
        query = query.filter(SimCard.status == status)
    if customer_id:
        query = query.filter(SimCard.customer_id == customer_id)
    return query
