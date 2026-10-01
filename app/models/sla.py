from datetime import datetime

from app.db.types import UTCDateTime
from sqlalchemy import String, Integer, Enum, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TicketCategory, TicketPriority, CustomerType


class SLARule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sla_rules"

    ticket_category: Mapped[TicketCategory] = mapped_column(Enum(TicketCategory), nullable=False)
    priority: Mapped[TicketPriority] = mapped_column(Enum(TicketPriority), nullable=False)
    customer_type: Mapped[CustomerType] = mapped_column(Enum(CustomerType), nullable=False)

    response_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class SLATracking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sla_tracking"

    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("tickets.id"), nullable=False, unique=True, index=True)
    sla_rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("sla_rules.id"), nullable=False)

    sla_start_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_time: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    breached: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
