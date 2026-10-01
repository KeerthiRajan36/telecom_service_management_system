from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, assert_customer_access
from app.services import subscription_service, sim_service
from app.db.session import get_db
from app.models.user import User
from app.schemas.usage import UsageRecordCreate, UsageRecordOut, UsageSummary
from app.services import usage_service
from app.workers import jobs

router = APIRouter(prefix="/usage", tags=["Usage Tracking"])


def _default_period(period_start: date | None, period_end: date | None) -> tuple[date, date]:
    today = date.today()
    return period_start or today.replace(day=1), period_end or today


@router.post("", response_model=UsageRecordOut, status_code=status.HTTP_201_CREATED)
def record_usage(
    payload: UsageRecordCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Records (or accumulates onto) a day's usage for a subscription.
    Crossing 80% / 100% of any quota raises a one-off usage-threshold notification."""
    record = usage_service.record_usage(db, payload)
    background_tasks.add_task(jobs.check_usage_thresholds_background, payload.subscription_id)
    return record


@router.get("/subscriptions/{subscription_id}/summary", response_model=UsageSummary)
def subscription_summary(
    subscription_id: str,
    period_start: date | None = None,
    period_end: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_customer_access(current_user, subscription_service.get_subscription(db, subscription_id).customer_id)
    start, end = _default_period(period_start, period_end)
    return usage_service.get_subscription_usage_summary(db, subscription_id, start, end)


@router.get("/sims/{sim_id}", response_model=list[UsageRecordOut])
def sim_usage(
    sim_id: str,
    period_start: date | None = None,
    period_end: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_customer_access(current_user, sim_service.get_sim(db, sim_id).customer_id)
    start, end = _default_period(period_start, period_end)
    return usage_service.get_sim_usage(db, sim_id, start, end)


@router.get("/customers/{customer_id}", response_model=list[UsageSummary])
def customer_usage(
    customer_id: str,
    period_start: date | None = None,
    period_end: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_customer_access(current_user, customer_id)
    start, end = _default_period(period_start, period_end)
    return usage_service.get_customer_usage(db, customer_id, start, end)


@router.get("/plans/{plan_id}/utilization")
def plan_utilization(
    plan_id: str,
    period_start: date | None = None,
    period_end: date | None = None,
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    start, end = _default_period(period_start, period_end)
    return usage_service.get_plan_utilization(db, plan_id, start, end)
