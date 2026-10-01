from datetime import datetime, date as date_type

from pydantic import BaseModel

from app.models.enums import TowerType, TowerStatus, EquipmentType, EquipmentStatus
from app.schemas.common import ORMModel


class TowerCreate(BaseModel):
    code: str
    name: str
    tower_type: TowerType = TowerType.MACRO
    latitude: float
    longitude: float
    coverage_radius_km: float = 5.0
    capacity: int = 1000


class TowerUpdate(BaseModel):
    name: str | None = None
    coverage_radius_km: float | None = None
    capacity: int | None = None
    status: TowerStatus | None = None


class TowerOut(ORMModel):
    id: str
    code: str
    name: str
    tower_type: TowerType
    latitude: float
    longitude: float
    coverage_radius_km: float
    capacity: int
    status: TowerStatus


class EquipmentCreate(BaseModel):
    tower_id: str
    name: str
    equipment_type: EquipmentType
    installation_date: date_type | None = None
    maintenance_schedule: date_type | None = None


class EquipmentHeartbeat(BaseModel):
    cpu_usage_percent: float
    memory_usage_percent: float
    status: EquipmentStatus = EquipmentStatus.ONLINE


class EquipmentOut(ORMModel):
    id: str
    tower_id: str
    name: str
    equipment_type: EquipmentType
    installation_date: date_type | None
    maintenance_schedule: date_type | None
    cpu_usage_percent: float
    memory_usage_percent: float
    status: EquipmentStatus
    last_heartbeat: datetime | None
