from datetime import datetime

from app.db.types import UTCDateTime
from sqlalchemy import String, Float, Enum, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TechnicianAvailability, AssignmentTargetType, AssignmentStatus


class Technician(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "technicians"

    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    skills: Mapped[str] = mapped_column(String(512), default="")  # comma-separated skill tags
    service_area: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability_status: Mapped[TechnicianAvailability] = mapped_column(
        Enum(TechnicianAvailability), default=TechnicianAvailability.AVAILABLE, index=True
    )


class TechnicianAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "technician_assignments"

    technician_id: Mapped[str] = mapped_column(String(36), ForeignKey("technicians.id"), nullable=False, index=True)
    target_type: Mapped[AssignmentTargetType] = mapped_column(Enum(AssignmentTargetType), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # ticket.id or outage.id
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus), default=AssignmentStatus.ASSIGNED, index=True)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
