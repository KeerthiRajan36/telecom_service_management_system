from datetime import date

from sqlalchemy import String, Boolean, Enum, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin, SoftDeleteMixin
from app.models.enums import KYCStatus, CustomerType


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "customers"

    customer_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_type: Mapped[CustomerType] = mapped_column(Enum(CustomerType), default=CustomerType.PREPAID)

    kyc_status: Mapped[KYCStatus] = mapped_column(Enum(KYCStatus), default=KYCStatus.PENDING, nullable=False)
    kyc_document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kyc_document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    addresses: Mapped[list["Address"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class Address(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "addresses"

    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(32), default="home")  # home/office/billing/shipping
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(128), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(128), default="India")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped["Customer"] = relationship(back_populates="addresses")
