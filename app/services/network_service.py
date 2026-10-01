from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.network import Tower, NetworkEquipment
from app.models.enums import TowerStatus, EquipmentStatus
from app.schemas.network import TowerCreate, TowerUpdate, EquipmentCreate, EquipmentHeartbeat
from app.utils.audit_logger import record_audit


def create_tower(db: Session, actor_id: str | None, payload: TowerCreate) -> Tower:
    if db.query(Tower).filter(Tower.code == payload.code).first():
        raise AppError("A tower with this code already exists", 409, "TOWER_EXISTS")
    tower = Tower(**payload.model_dump())
    db.add(tower)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="Tower", entity_id=tower.id, new_value={"code": tower.code})
    db.commit()
    db.refresh(tower)
    return tower


def get_tower(db: Session, tower_id: str) -> Tower:
    tower = db.get(Tower, tower_id)
    if not tower:
        raise NotFoundError("Tower not found")
    return tower


def update_tower(db: Session, actor_id: str | None, tower_id: str, payload: TowerUpdate) -> Tower:
    tower = get_tower(db, tower_id)
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(tower, k) for k in data}
    for field, value in data.items():
        setattr(tower, field, value)
    record_audit(db, user_id=actor_id, action="UPDATE", entity="Tower", entity_id=tower.id, previous_value=before, new_value=data)
    db.commit()
    db.refresh(tower)
    return tower


def set_tower_status(db: Session, actor_id: str | None, tower_id: str, status: TowerStatus) -> Tower:
    tower = get_tower(db, tower_id)
    before = tower.status.value
    tower.status = status
    record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="Tower", entity_id=tower.id, previous_value={"status": before}, new_value={"status": status.value})
    db.commit()
    db.refresh(tower)
    return tower


def query_towers(db: Session, status: TowerStatus | None = None):
    query = db.query(Tower)
    if status:
        query = query.filter(Tower.status == status)
    return query


# ---- Network Equipment ----

def create_equipment(db: Session, actor_id: str | None, payload: EquipmentCreate) -> NetworkEquipment:
    if not db.get(Tower, payload.tower_id):
        raise NotFoundError("Tower not found")
    equipment = NetworkEquipment(**payload.model_dump())
    db.add(equipment)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="NetworkEquipment", entity_id=equipment.id, new_value={"tower_id": equipment.tower_id})
    db.commit()
    db.refresh(equipment)
    return equipment


def get_equipment(db: Session, equipment_id: str) -> NetworkEquipment:
    equipment = db.get(NetworkEquipment, equipment_id)
    if not equipment:
        raise NotFoundError("Equipment not found")
    return equipment


def record_heartbeat(db: Session, equipment_id: str, payload: EquipmentHeartbeat) -> NetworkEquipment:
    """Called periodically by monitoring agents. Updates health metrics and
    flips status automatically if thresholds are breached."""
    equipment = get_equipment(db, equipment_id)
    equipment.cpu_usage_percent = payload.cpu_usage_percent
    equipment.memory_usage_percent = payload.memory_usage_percent
    equipment.status = payload.status
    equipment.last_heartbeat = datetime.now(timezone.utc)
    db.commit()
    db.refresh(equipment)
    return equipment


def get_stale_equipment(db: Session, stale_after_minutes: int = 15) -> list[NetworkEquipment]:
    """Equipment that hasn't sent a heartbeat recently -> likely down."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_after_minutes)
    return (
        db.query(NetworkEquipment)
        .filter((NetworkEquipment.last_heartbeat.is_(None)) | (NetworkEquipment.last_heartbeat < cutoff))
        .all()
    )


def query_equipment(db: Session, tower_id: str | None = None, status: EquipmentStatus | None = None):
    query = db.query(NetworkEquipment)
    if tower_id:
        query = query.filter(NetworkEquipment.tower_id == tower_id)
    if status:
        query = query.filter(NetworkEquipment.status == status)
    return query
