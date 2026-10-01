from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import OutageType, OutageSeverity, OutageStatus
from app.schemas.common import ORMModel


class OutageCreate(BaseModel):
    title: str
    description: str | None = None
    outage_type: OutageType = OutageType.UNPLANNED
    severity: OutageSeverity
    tower_ids: list[str] = Field(min_length=1)
    start_time: datetime
    expected_resolution: datetime | None = None


class OutageResolve(BaseModel):
    actual_resolution: datetime | None = None
    resolution_notes: str | None = None


class OutageOut(ORMModel):
    id: str
    title: str
    description: str | None
    outage_type: OutageType
    severity: OutageSeverity
    status: OutageStatus
    start_time: datetime
    expected_resolution: datetime | None
    actual_resolution: datetime | None
    tower_ids: list[str] = []


class AffectedCustomerOut(ORMModel):
    customer_id: str
    notified: bool
