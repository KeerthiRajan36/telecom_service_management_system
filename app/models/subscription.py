from datetime import datetime

from app.db.types import UTCDateTime
from sqlalchemy import String, Enum, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SubscriptionStatus


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    sim_id: Mapped[str] = mapped_column(String(36), ForeignKey("sim_cards.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_plans.id"), nullable=False, index=True)

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False, index=True
    )
    start_date: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(default=True)


class SubscriptionHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):

    __tablename__ = "subscription_history"

    subscription_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # created/upgraded/downgraded/renewed/suspended/reactivated/cancelled
    from_plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_plans.id"), nullable=True)
    to_plan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_plans.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
