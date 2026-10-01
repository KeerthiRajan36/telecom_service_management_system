from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import KYCStatus, CustomerType
from app.schemas.common import ORMModel


class AddressCreate(BaseModel):
    label: str = "home"
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str = "India"
    is_primary: bool = False


class AddressOut(ORMModel):
    id: str
    label: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_primary: bool


class CustomerCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    date_of_birth: date | None = None
    customer_type: CustomerType = CustomerType.PREPAID
    kyc_document_type: str | None = None
    kyc_document_number: str | None = None
    address: AddressCreate | None = None


class CustomerUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    customer_type: CustomerType | None = None


class KYCUpdate(BaseModel):
    kyc_status: KYCStatus
    kyc_document_type: str | None = None
    kyc_document_number: str | None = None


class CustomerOut(ORMModel):
    id: str
    customer_code: str
    full_name: str
    email: str
    phone: str
    date_of_birth: date | None
    customer_type: CustomerType
    kyc_status: KYCStatus
    is_active: bool
    created_at: datetime
    addresses: list[AddressOut] = []


class CustomerListItem(ORMModel):
    id: str
    customer_code: str
    full_name: str
    email: str
    phone: str
    customer_type: CustomerType
    kyc_status: KYCStatus
    is_active: bool
