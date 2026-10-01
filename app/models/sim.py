from datetime import datetime

from app.db.types import UTCDateTime
from sqlalchemy import String, Enum, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SimType, SimStatus


class SimCard(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sim_cards"

    sim_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)  # ICCID / MSISDN
    sim_type: Mapped[SimType] = mapped_column(Enum(SimType), default=SimType.PHYSICAL, nullable=False)
    status: Mapped[SimStatus] = mapped_column(Enum(SimStatus), default=SimStatus.AVAILABLE, nullable=False, index=True)

    activation_date: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    current_plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_plans.id"), nullable=True)

    serving_tower_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("towers.id"), nullable=True, index=True)


class SimReplacement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sim_replacements"

    old_sim_id: Mapped[str] = mapped_column(String(36), ForeignKey("sim_cards.id"), nullable=False)
    new_sim_id: Mapped[str] = mapped_column(String(36), ForeignKey("sim_cards.id"), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
