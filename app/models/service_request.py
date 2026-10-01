from sqlalchemy import String, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ServiceRequestType, ServiceRequestStatus


class ServiceRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_requests"

    request_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    request_type: Mapped[ServiceRequestType] = mapped_column(Enum(ServiceRequestType), nullable=False)
    status: Mapped[ServiceRequestStatus] = mapped_column(
        Enum(ServiceRequestStatus), default=ServiceRequestStatus.SUBMITTED, index=True
    )
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    history: Mapped[list["ServiceRequestHistory"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class ServiceRequestHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_request_history"

    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_requests.id"), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped["ServiceRequest"] = relationship(back_populates="history")
