from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.device import Device
from app.models.sim import SimCard
from app.models.customer import Customer
from app.models.enums import DeviceStatus, SimStatus
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.utils.audit_logger import record_audit
from app.services import customer_service


def _validate_sim_assignable(db: Session, sim_id: str, customer_id: str | None = None) -> SimCard:
    sim = db.get(SimCard, sim_id)
    if not sim:
        raise NotFoundError("SIM not found")
    if sim.status not in (SimStatus.ACTIVE, SimStatus.AVAILABLE):
        raise AppError(f"SIM is {sim.status.value} and cannot be assigned to a device", 409, "INVALID_SIM_ASSIGNMENT")
    if customer_id and sim.customer_id and sim.customer_id != customer_id:
        raise AppError("SIM belongs to a different customer than the device", 409, "INVALID_SIM_ASSIGNMENT")
    existing = db.query(Device).filter(Device.sim_id == sim_id).first()
    if existing:
        raise AppError("This SIM is already mapped to another device", 409, "SIM_ALREADY_MAPPED")
    return sim


def create_device(db: Session, actor_id: str | None, payload: DeviceCreate) -> Device:
    if db.query(Device).filter(Device.imei == payload.imei).first():
        raise AppError("Duplicate IMEI: a device with this IMEI is already registered", 409, "DUPLICATE_IMEI")

    if payload.customer_id:
        customer_service.get_customer(db, payload.customer_id)  # 404 if missing/deleted

    if payload.sim_id:
        _validate_sim_assignable(db, payload.sim_id, payload.customer_id)

    device = Device(**payload.model_dump())
    db.add(device)
    db.flush()
    record_audit(db, user_id=actor_id, action="CREATE", entity="Device", entity_id=device.id, new_value={"imei": device.imei})
    db.commit()
    db.refresh(device)
    return device


def get_device(db: Session, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if not device:
        raise NotFoundError("Device not found")
    return device


def update_device(db: Session, actor_id: str | None, device_id: str, payload: DeviceUpdate) -> Device:
    device = get_device(db, device_id)
    data = payload.model_dump(exclude_unset=True)
    before = {k: getattr(device, k) for k in data}
    for field, value in data.items():
        setattr(device, field, value)
    record_audit(db, user_id=actor_id, action="UPDATE", entity="Device", entity_id=device.id, previous_value=before, new_value=data)
    db.commit()
    db.refresh(device)
    return device


def assign_sim(db: Session, actor_id: str | None, device_id: str, sim_id: str) -> Device:
    device = get_device(db, device_id)
    _validate_sim_assignable(db, sim_id, device.customer_id)
    device.sim_id = sim_id
    record_audit(db, user_id=actor_id, action="ASSIGN_SIM", entity="Device", entity_id=device.id, new_value={"sim_id": sim_id})
    db.commit()
    db.refresh(device)
    return device


def query_devices(db: Session, status: DeviceStatus | None = None, customer_id: str | None = None):
    query = db.query(Device)
    if status:
        query = query.filter(Device.status == status)
    if customer_id:
        query = query.filter(Device.customer_id == customer_id)
    return query
