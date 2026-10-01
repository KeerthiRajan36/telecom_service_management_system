from datetime import datetime

from app.db.types import UTCDateTime
from sqlalchemy import String, Enum, DateTime, ForeignKey, Text, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutageType, OutageSeverity, OutageStatus
from app.models.network import Tower

outage_tower_association = Table(
    "outage_towers",
    Base.metadata,
    Column("outage_id", String(36), ForeignKey("outages.id"), primary_key=True),
    Column("tower_id", String(36), ForeignKey("towers.id"), primary_key=True),
)


class Outage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "outages"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    outage_type: Mapped[OutageType] = mapped_column(Enum(OutageType), default=OutageType.UNPLANNED)
    severity: Mapped[OutageSeverity] = mapped_column(Enum(OutageSeverity), nullable=False, index=True)
    status: Mapped[OutageStatus] = mapped_column(Enum(OutageStatus), default=OutageStatus.OPEN, index=True)

    start_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expected_resolution: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    actual_resolution: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    towers: Mapped[list[Tower]] = relationship(secondary=outage_tower_association)


class OutageAffectedCustomer(Base, UUIDPrimaryKeyMixin, TimestampMixin):

    __tablename__ = "outage_affected_customers"

    outage_id: Mapped[str] = mapped_column(String(36), ForeignKey("outages.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    notified: Mapped[bool] = mapped_column(default=False)
