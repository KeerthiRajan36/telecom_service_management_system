from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.service_request import ServiceRequest, ServiceRequestHistory
from app.models.customer import Customer
from app.models.enums import ServiceRequestStatus
from app.schemas.service_request import ServiceRequestCreate
from app.utils.codes import gen_request_code
from app.utils.audit_logger import record_audit
from app.services import customer_service


_TERMINAL = {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.REJECTED}


def create_request(db: Session, actor_id: str | None, payload: ServiceRequestCreate) -> ServiceRequest:
    customer_service.get_customer(db, payload.customer_id)  # 404 if missing/deleted

    request = ServiceRequest(
        request_code=gen_request_code(),
        customer_id=payload.customer_id,
        request_type=payload.request_type,
        details=payload.details,
        payload=payload.payload,
        status=ServiceRequestStatus.SUBMITTED,
    )
    db.add(request)
    db.flush()

    db.add(ServiceRequestHistory(request_id=request.id, from_status=None, to_status=ServiceRequestStatus.SUBMITTED.value))
    record_audit(db, user_id=actor_id, action="CREATE", entity="ServiceRequest", entity_id=request.id, new_value={"request_type": request.request_type.value})
    db.commit()
    db.refresh(request)
    return request


def get_request(db: Session, request_id: str) -> ServiceRequest:
    request = db.get(ServiceRequest, request_id)
    if not request:
        raise NotFoundError("Service request not found")
    return request


def update_status(db: Session, actor_id: str | None, request_id: str, new_status: ServiceRequestStatus, notes: str | None = None) -> ServiceRequest:
    request = get_request(db, request_id)
    if request.status in _TERMINAL:
        raise AppError(f"Request is already {request.status.value} and can no longer change", 409, "INVALID_TRANSITION")
    before = request.status.value
    request.status = new_status

    db.add(ServiceRequestHistory(request_id=request.id, from_status=before, to_status=new_status.value, notes=notes))
    record_audit(db, user_id=actor_id, action="STATUS_CHANGE", entity="ServiceRequest", entity_id=request.id, previous_value={"status": before}, new_value={"status": new_status.value})
    db.commit()
    db.refresh(request)
    return request


def get_history(db: Session, request_id: str) -> list[ServiceRequestHistory]:
    get_request(db, request_id)
    return db.query(ServiceRequestHistory).filter(ServiceRequestHistory.request_id == request_id).order_by(ServiceRequestHistory.created_at.desc()).all()


def query_requests(db: Session, customer_id: str | None = None, status: ServiceRequestStatus | None = None, request_type=None):
    query = db.query(ServiceRequest)
    if customer_id:
        query = query.filter(ServiceRequest.customer_id == customer_id)
    if status:
        query = query.filter(ServiceRequest.status == status)
    if request_type:
        query = query.filter(ServiceRequest.request_type == request_type)
    return query
