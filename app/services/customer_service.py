from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.core.exceptions import AppError, NotFoundError
from app.models.customer import Customer, Address
from app.models.audit import AuditLog
from app.models.enums import KYCStatus
from app.schemas.customer import CustomerCreate, CustomerUpdate, KYCUpdate, AddressCreate
from app.utils.codes import gen_customer_code
from app.utils.audit_logger import record_audit


def create_customer(db: Session, actor_id: str | None, payload: CustomerCreate) -> Customer:
    if db.query(Customer).filter(Customer.email == payload.email).first():
        raise AppError("A customer with this email already exists", 409, "CUSTOMER_EXISTS")
    if db.query(Customer).filter(Customer.phone == payload.phone).first():
        raise AppError("A customer with this phone number already exists", 409, "CUSTOMER_EXISTS")

    customer = Customer(
        customer_code=gen_customer_code(),
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        date_of_birth=payload.date_of_birth,
        customer_type=payload.customer_type,
        kyc_document_type=payload.kyc_document_type,
        kyc_document_number=payload.kyc_document_number,
    )
    db.add(customer)
    db.flush()

    if payload.address:
        addr = Address(customer_id=customer.id, **payload.address.model_dump())
        db.add(addr)

    record_audit(db, user_id=actor_id, action="CREATE", entity="Customer", entity_id=customer.id, new_value=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(customer)
    return customer


def get_customer(db: Session, customer_id: str) -> Customer:
    customer = (
        db.query(Customer)
        .options(selectinload(Customer.addresses))
        .filter(Customer.id == customer_id, Customer.is_deleted.is_(False))
        .first()
    )
    if not customer:
        raise NotFoundError("Customer not found")
    return customer


def update_customer(db: Session, actor_id: str | None, customer_id: str, payload: CustomerUpdate) -> Customer:
    customer = get_customer(db, customer_id)
    before = {"full_name": customer.full_name, "email": customer.email, "phone": customer.phone}
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(customer, field, value)

    record_audit(db, user_id=actor_id, action="UPDATE", entity="Customer", entity_id=customer.id, previous_value=before, new_value=data)
    db.commit()
    db.refresh(customer)
    return customer


def add_address(db: Session, actor_id: str | None, customer_id: str, payload: AddressCreate) -> Address:
    customer = get_customer(db, customer_id)
    if payload.is_primary:
        for a in customer.addresses:
            a.is_primary = False
    addr = Address(customer_id=customer.id, **payload.model_dump())
    db.add(addr)
    record_audit(db, user_id=actor_id, action="ADD_ADDRESS", entity="Customer", entity_id=customer.id, new_value=payload.model_dump())
    db.commit()
    db.refresh(addr)
    return addr


def update_kyc(db: Session, actor_id: str | None, customer_id: str, payload: KYCUpdate) -> Customer:
    customer = get_customer(db, customer_id)
    before = {"kyc_status": customer.kyc_status.value}
    customer.kyc_status = payload.kyc_status
    if payload.kyc_document_type:
        customer.kyc_document_type = payload.kyc_document_type
    if payload.kyc_document_number:
        customer.kyc_document_number = payload.kyc_document_number

    record_audit(db, user_id=actor_id, action="KYC_UPDATE", entity="Customer", entity_id=customer.id, previous_value=before, new_value={"kyc_status": payload.kyc_status.value})
    db.commit()
    db.refresh(customer)
    return customer


def set_customer_active(db: Session, actor_id: str | None, customer_id: str, is_active: bool) -> Customer:
    customer = get_customer(db, customer_id)
    before = customer.is_active
    customer.is_active = is_active
    record_audit(
        db,
        user_id=actor_id,
        action="ACTIVATE" if is_active else "DEACTIVATE",
        entity="Customer",
        entity_id=customer.id,
        previous_value={"is_active": before},
        new_value={"is_active": is_active},
    )
    db.commit()
    db.refresh(customer)
    return customer


def soft_delete_customer(db: Session, actor_id: str | None, customer_id: str) -> None:
    customer = get_customer(db, customer_id)
    from datetime import datetime, timezone

    customer.is_deleted = True
    customer.deleted_at = datetime.now(timezone.utc)
    record_audit(db, user_id=actor_id, action="DELETE", entity="Customer", entity_id=customer.id)
    db.commit()


def query_customers(db: Session, kyc_status: KYCStatus | None = None, customer_type=None, is_active: bool | None = None):
    query = db.query(Customer).filter(Customer.is_deleted.is_(False))
    if kyc_status:
        query = query.filter(Customer.kyc_status == kyc_status)
    if customer_type:
        query = query.filter(Customer.customer_type == customer_type)
    if is_active is not None:
        query = query.filter(Customer.is_active == is_active)
    return query


def get_customer_history(db: Session, customer_id: str) -> list[AuditLog]:
    get_customer(db, customer_id)  # 404 if missing
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity == "Customer", AuditLog.entity_id == customer_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
