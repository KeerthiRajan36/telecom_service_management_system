from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ServiceRequestType, ServiceRequestStatus
from app.schemas.common import ORMModel


class ServiceRequestCreate(BaseModel):
    customer_id: str
    request_type: ServiceRequestType
    details: str | None = None
    payload: str | None = None


class ServiceRequestStatusUpdate(BaseModel):
    status: ServiceRequestStatus
    notes: str | None = None


class ServiceRequestOut(ORMModel):
    id: str
    request_code: str
    customer_id: str
    request_type: ServiceRequestType
    status: ServiceRequestStatus
    details: str | None
    payload: str | None
    created_at: datetime


class ServiceRequestHistoryOut(ORMModel):
    id: str
    request_id: str
    from_status: str | None
    to_status: str
    notes: str | None
    created_at: datetime
