from pydantic import BaseModel, Field

from app.models.enums import PlanType, PlanCategory, PlanStatus
from app.schemas.common import ORMModel


class PlanCreate(BaseModel):
    name: str
    code: str
    description: str | None = None
    plan_type: PlanType
    category: PlanCategory
    price: float = Field(gt=0)
    validity_days: int = Field(gt=0)
    data_limit_mb: int | None = None
    voice_limit_minutes: int | None = None
    sms_limit_count: int | None = None
    is_featured: bool = False


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    validity_days: int | None = None
    data_limit_mb: int | None = None
    voice_limit_minutes: int | None = None
    sms_limit_count: int | None = None
    is_featured: bool | None = None


class PlanOut(ORMModel):
    id: str
    name: str
    code: str
    description: str | None
    plan_type: PlanType
    category: PlanCategory
    price: float
    validity_days: int
    data_limit_mb: int | None
    voice_limit_minutes: int | None
    sms_limit_count: int | None
    status: PlanStatus
    is_featured: bool


class PlanCompareRequest(BaseModel):
    plan_ids: list[str] = Field(min_length=2, max_length=5)
