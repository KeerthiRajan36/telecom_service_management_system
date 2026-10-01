from sqlalchemy import String, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # CREATE/UPDATE/DELETE/LOGIN/...
    entity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # e.g. "Customer", "Ticket"
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
