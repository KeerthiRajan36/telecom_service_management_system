from datetime import datetime, date as date_type

from app.db.types import UTCDateTime
from sqlalchemy import String, Float, Integer, Enum, DateTime, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TowerType, TowerStatus, EquipmentType, EquipmentStatus


class Tower(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "towers"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tower_type: Mapped[TowerType] = mapped_column(Enum(TowerType), default=TowerType.MACRO)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_radius_km: Mapped[float] = mapped_column(Float, default=5.0)
    capacity: Mapped[int] = mapped_column(Integer, default=1000)  # max simultaneous connections
    status: Mapped[TowerStatus] = mapped_column(Enum(TowerStatus), default=TowerStatus.ACTIVE, index=True)


class NetworkEquipment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "network_equipment"

    tower_id: Mapped[str] = mapped_column(String(36), ForeignKey("towers.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    equipment_type: Mapped[EquipmentType] = mapped_column(Enum(EquipmentType), nullable=False)
    installation_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    maintenance_schedule: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    cpu_usage_percent: Mapped[float] = mapped_column(Float, default=0.0)
    memory_usage_percent: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[EquipmentStatus] = mapped_column(Enum(EquipmentStatus), default=EquipmentStatus.ONLINE, index=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
