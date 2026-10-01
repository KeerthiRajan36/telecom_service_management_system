from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, require_support_staff
from app.db.session import get_db
from app.models.user import User
from app.models.service_request import ServiceRequest
from app.models.enums import ServiceRequestStatus, ServiceRequestType, UserRole
from app.schemas.service_request import (
    ServiceRequestCreate, ServiceRequestStatusUpdate, ServiceRequestOut, ServiceRequestHistoryOut,
)
from app.schemas.common import PaginatedResponse
from app.services import service_request_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/service-requests", tags=["Service Requests"])


@router.post("", response_model=ServiceRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(payload: ServiceRequestCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.CUSTOMER and current_user.customer_id != payload.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customers can only create requests for their own account")
    return service_request_service.create_request(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[ServiceRequestOut])
def list_requests(
    customer_id: str | None = None,
    request_status: ServiceRequestStatus | None = None,
    request_type: ServiceRequestType | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == UserRole.CUSTOMER:
        customer_id = current_user.customer_id
    query = service_request_service.query_requests(db, customer_id, request_status, request_type)
    return paginate(query, params, ServiceRequestOut, ServiceRequest, search_fields=["request_code", "details"])


@router.get("/{request_id}", response_model=ServiceRequestOut)
def get_request(request_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request = service_request_service.get_request(db, request_id)
    if current_user.role == UserRole.CUSTOMER and current_user.customer_id != request.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own requests")
    return request


@router.patch("/{request_id}/status", response_model=ServiceRequestOut)
def update_status(request_id: str, payload: ServiceRequestStatusUpdate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return service_request_service.update_status(db, current_user.id, request_id, payload.status, payload.notes)


@router.get("/{request_id}/history", response_model=list[ServiceRequestHistoryOut])
def get_history(request_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return service_request_service.get_history(db, request_id)
