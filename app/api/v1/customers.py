from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, require_support_staff, assert_customer_access
from app.db.session import get_db
from app.models.user import User
from app.models.enums import KYCStatus, CustomerType
from app.schemas.customer import CustomerCreate, CustomerUpdate, KYCUpdate, CustomerOut, AddressCreate, AddressOut
from app.schemas.auth import ActivationRequest
from app.schemas.audit import AuditLogOut
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import customer_service
from app.utils.pagination import PageParams, paginate
from app.models.customer import Customer

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return customer_service.create_customer(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[CustomerOut])
def list_customers(
    kyc_status: KYCStatus | None = None,
    customer_type: CustomerType | None = None,
    is_active: bool | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = customer_service.query_customers(db, kyc_status, customer_type, is_active)
    return paginate(query, params, CustomerOut, Customer, search_fields=["full_name", "email", "phone", "customer_code"])


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_customer_access(current_user, customer_id)
    return customer_service.get_customer(db, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, payload: CustomerUpdate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return customer_service.update_customer(db, current_user.id, customer_id, payload)


@router.post("/{customer_id}/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def add_address(customer_id: str, payload: AddressCreate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return customer_service.add_address(db, current_user.id, customer_id, payload)


@router.patch("/{customer_id}/kyc", response_model=CustomerOut)
def update_kyc(customer_id: str, payload: KYCUpdate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return customer_service.update_kyc(db, current_user.id, customer_id, payload)


@router.patch("/{customer_id}/activation", response_model=CustomerOut)
def set_activation(customer_id: str, payload: ActivationRequest, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return customer_service.set_customer_active(db, current_user.id, customer_id, payload.is_active)


@router.delete("/{customer_id}", response_model=MessageResponse)
def delete_customer(customer_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    customer_service.soft_delete_customer(db, current_user.id, customer_id)
    return MessageResponse(message="Customer deleted (soft delete)")


@router.get("/{customer_id}/history", response_model=list[AuditLogOut])
def customer_history(customer_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return customer_service.get_customer_history(db, customer_id)
