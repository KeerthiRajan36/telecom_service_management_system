from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SubscriptionStatus
from app.schemas.common import ORMModel


class SubscriptionCreate(BaseModel):
    customer_id: str
    sim_id: str
    plan_id: str
    auto_renew: bool = True


class SubscriptionPlanChange(BaseModel):
    new_plan_id: str
    notes: str | None = None


class SubscriptionOut(ORMModel):
    id: str
    customer_id: str
    sim_id: str
    plan_id: str
    status: SubscriptionStatus
    start_date: datetime
    end_date: datetime | None
    auto_renew: bool


class SubscriptionHistoryOut(ORMModel):
    id: str
    subscription_id: str
    action: str
    from_plan_id: str | None
    to_plan_id: str | None
    notes: str | None
    created_at: datetime
