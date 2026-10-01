from datetime import date as date_type

from sqlalchemy import String, Float, Integer, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UsageRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):

    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("subscription_id", "usage_date", name="uq_subscription_date"),)

    subscription_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    sim_id: Mapped[str] = mapped_column(String(36), ForeignKey("sim_cards.id"), nullable=False, index=True)
    usage_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    data_used_mb: Mapped[float] = mapped_column(Float, default=0.0)
    voice_used_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    sms_used_count: Mapped[int] = mapped_column(Integer, default=0)
