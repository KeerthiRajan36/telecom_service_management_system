from datetime import date as date_type

from pydantic import BaseModel

from app.schemas.common import ORMModel


class UsageRecordCreate(BaseModel):
    subscription_id: str
    usage_date: date_type
    data_used_mb: float = 0.0
    voice_used_minutes: float = 0.0
    sms_used_count: int = 0


class UsageRecordOut(ORMModel):
    id: str
    subscription_id: str
    sim_id: str
    usage_date: date_type
    data_used_mb: float
    voice_used_minutes: float
    sms_used_count: int


class UsageSummary(BaseModel):
    subscription_id: str
    plan_id: str
    period_start: date_type
    period_end: date_type
    total_data_used_mb: float
    total_voice_used_minutes: float
    total_sms_used_count: int
    data_limit_mb: int | None
    voice_limit_minutes: int | None
    sms_limit_count: int | None
    data_usage_percent: float | None
    voice_usage_percent: float | None
    sms_usage_percent: float | None
    data_remaining_mb: float | None
    voice_remaining_minutes: float | None
    sms_remaining_count: int | None
