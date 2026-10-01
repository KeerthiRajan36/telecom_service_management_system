from sqlalchemy import String, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DeviceType, DeviceStatus


class Device(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "devices"

    imei: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType), default=DeviceType.SMARTPHONE)
    status: Mapped[DeviceStatus] = mapped_column(Enum(DeviceStatus), default=DeviceStatus.ACTIVE)

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    sim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sim_cards.id"), nullable=True, unique=True)
