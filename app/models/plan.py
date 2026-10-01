from sqlalchemy import String, Float, Integer, Enum, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PlanType, PlanCategory, PlanStatus


class ServicePlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_plans"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan_type: Mapped[PlanType] = mapped_column(Enum(PlanType), nullable=False)
    category: Mapped[PlanCategory] = mapped_column(Enum(PlanCategory), nullable=False)

    price: Mapped[float] = mapped_column(Float, nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False)

    data_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null == unlimited
    voice_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_limit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.ACTIVE, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
