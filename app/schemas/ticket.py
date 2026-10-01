from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TicketCategory, TicketStatus, TicketPriority
from app.schemas.common import ORMModel


class TicketCreate(BaseModel):
    customer_id: str
    category: TicketCategory
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM
    related_sim_id: str | None = None
    related_device_id: str | None = None


class TicketAssignAgent(BaseModel):
    agent_id: str


class TicketAssignTechnician(BaseModel):
    technician_id: str


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    resolution_notes: str | None = None


class TicketPriorityUpdate(BaseModel):
    priority: TicketPriority


class TicketEscalate(BaseModel):
    reason: str | None = None


class CommentCreate(BaseModel):
    body: str
    is_internal: bool = False


class CommentOut(ORMModel):
    id: str
    ticket_id: str
    author_id: str
    is_internal: bool
    body: str
    created_at: datetime


class TicketOut(ORMModel):
    id: str
    ticket_code: str
    customer_id: str
    category: TicketCategory
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    assigned_agent_id: str | None
    assigned_technician_id: str | None
    escalated: bool
    resolution_notes: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime


class TicketHistoryOut(ORMModel):
    id: str
    ticket_id: str
    action: str
    actor_id: str | None
    from_value: str | None
    to_value: str | None
    created_at: datetime
