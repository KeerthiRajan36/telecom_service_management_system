from datetime import datetime

from app.db.types import UTCDateTime
from sqlalchemy import String, Enum, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TicketCategory, TicketStatus, TicketPriority


class Ticket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tickets"

    ticket_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    category: Mapped[TicketCategory] = mapped_column(Enum(TicketCategory), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.OPEN, index=True)
    priority: Mapped[TicketPriority] = mapped_column(Enum(TicketPriority), default=TicketPriority.MEDIUM, index=True)

    assigned_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    assigned_technician_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("technicians.id"), nullable=True)

    related_sim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sim_cards.id"), nullable=True)
    related_device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)

    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    comments: Mapped[list["TicketComment"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ticket_comments"

    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("tickets.id"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)  # internal note vs customer-visible
    body: Mapped[str] = mapped_column(Text, nullable=False)

    ticket: Mapped["Ticket"] = relationship(back_populates="comments")


class TicketHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Every status/priority/assignment transition of a ticket."""
    __tablename__ = "ticket_history"

    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("tickets.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    from_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
