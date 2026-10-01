from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TicketCategory, TicketPriority, CustomerType
from app.schemas.common import ORMModel


class SLARuleCreate(BaseModel):
    ticket_category: TicketCategory
    priority: TicketPriority
    customer_type: CustomerType
    response_time_minutes: int
    resolution_time_minutes: int


class SLARuleOut(ORMModel):
    id: str
    ticket_category: TicketCategory
    priority: TicketPriority
    customer_type: CustomerType
    response_time_minutes: int
    resolution_time_minutes: int


class SLATrackingOut(ORMModel):
    id: str
    ticket_id: str
    sla_rule_id: str
    sla_start_time: datetime
    sla_deadline: datetime
    resolved_time: datetime | None
    breached: bool
    escalated: bool
