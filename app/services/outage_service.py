from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.outage import Outage, OutageAffectedCustomer
from app.models.network import Tower
from app.models.sim import SimCard
from app.models.enums import OutageStatus, OutageType, SimStatus, TowerStatus
from app.schemas.outage import OutageCreate, OutageResolve
from app.utils.audit_logger import record_audit


def _identify_affected_customers(db: Session, outage: Outage) -> list[str]:
    """Level 10 requirement: automatically identify affected customers based
    on tower/service mapping. A customer is affected if one of their active
    SIMs is currently served by one of the outage's towers."""
    tower_ids = [t.id for t in outage.towers]
    if not tower_ids:
        return []

    affected_sims = (
        db.query(SimCard)
        .filter(SimCard.serving_tower_id.in_(tower_ids), SimCard.status == SimStatus.ACTIVE, SimCard.customer_id.isnot(None))
        .all()
    )
    customer_ids = sorted({sim.customer_id for sim in affected_sims})

    for cid in customer_ids:
        db.add(OutageAffectedCustomer(outage_id=outage.id, customer_id=cid))

    return customer_ids


def create_outage(db: Session, actor_id: str | None, payload: OutageCreate) -> Outage:
    towers = db.query(Tower).filter(Tower.id.in_(payload.tower_ids)).all()
    found_ids = {t.id for t in towers}
    missing = set(payload.tower_ids) - found_ids
    if missing:
        raise NotFoundError(f"Tower(s) not found: {', '.join(missing)}")

    outage = Outage(
        title=payload.title,
        description=payload.description,
        outage_type=payload.outage_type,
        severity=payload.severity,
        status=OutageStatus.OPEN,
        start_time=payload.start_time,
        expected_resolution=payload.expected_resolution,
    )
    outage.towers = towers
    db.add(outage)
    db.flush()

    # An unplanned outage takes healthy towers offline; a planned one puts them into maintenance.
    # Decommissioned / already-degraded towers are left untouched.
    new_tower_status = TowerStatus.OFFLINE if payload.outage_type == OutageType.UNPLANNED else TowerStatus.MAINTENANCE
    for tower in towers:
        if tower.status == TowerStatus.ACTIVE:
            record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="Tower", entity_id=tower.id,
                         previous_value={"status": tower.status.value}, new_value={"status": new_tower_status.value, "reason": f"outage {outage.id}"})
            tower.status = new_tower_status


    affected = _identify_affected_customers(db, outage)

    record_audit(
        db,
        user_id=actor_id,
        action="CREATE",
        entity="Outage",
        entity_id=outage.id,
        new_value={"severity": outage.severity.value, "tower_ids": list(found_ids), "affected_customers": len(affected)},
    )
    db.commit()
    db.refresh(outage)
    return outage


def get_outage(db: Session, outage_id: str) -> Outage:
    outage = db.get(Outage, outage_id)
    if not outage:
        raise NotFoundError("Outage not found")
    return outage


def get_affected_customers(db: Session, outage_id: str) -> list[OutageAffectedCustomer]:
    get_outage(db, outage_id)
    return db.query(OutageAffectedCustomer).filter(OutageAffectedCustomer.outage_id == outage_id).all()


def mark_in_progress(db: Session, actor_id: str | None, outage_id: str) -> Outage:
    outage = get_outage(db, outage_id)
    if outage.status != OutageStatus.OPEN:
        raise AppError(f"Cannot move outage from {outage.status.value} to in_progress", 409, "INVALID_TRANSITION")
    outage.status = OutageStatus.IN_PROGRESS
    record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="Outage", entity_id=outage.id, new_value={"status": "in_progress"})
    db.commit()
    db.refresh(outage)
    return outage


def resolve_outage(db: Session, actor_id: str | None, outage_id: str, payload: OutageResolve) -> Outage:
    """Resolving an outage also restores the towers to ACTIVE (service restoration)."""
    outage = get_outage(db, outage_id)
    if outage.status == OutageStatus.RESOLVED:
        raise AppError("Outage is already resolved", 409, "ALREADY_RESOLVED")

    outage.status = OutageStatus.RESOLVED
    outage.actual_resolution = payload.actual_resolution or datetime.now(timezone.utc)

    db.flush()
    for tower in outage.towers:
        if tower.status not in (TowerStatus.OFFLINE, TowerStatus.MAINTENANCE):
            continue
        # Don't restore a tower that is still covered by another unresolved outage.
        still_affected = (
            db.query(Outage).join(Outage.towers)
            .filter(Tower.id == tower.id, Outage.id != outage.id, Outage.status != OutageStatus.RESOLVED)
            .count()
        )
        if still_affected == 0:
            record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="Tower", entity_id=tower.id,
                         previous_value={"status": tower.status.value}, new_value={"status": "active", "reason": f"outage {outage.id} resolved"})
            tower.status = TowerStatus.ACTIVE

    record_audit(db, user_id=actor_id, action="RESOLVE", entity="Outage", entity_id=outage.id, new_value={"actual_resolution": outage.actual_resolution.isoformat()})
    db.commit()
    db.refresh(outage)
    return outage


def query_outages(db: Session, status: OutageStatus | None = None, severity=None):
    query = db.query(Outage)
    if status:
        query = query.filter(Outage.status == status)
    if severity:
        query = query.filter(Outage.severity == severity)
    return query
