from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.usage import UsageRecord
from app.models.subscription import Subscription
from app.models.plan import ServicePlan
from app.models.sim import SimCard
from app.schemas.usage import UsageRecordCreate, UsageSummary


def record_usage(db: Session, payload: UsageRecordCreate) -> UsageRecord:
    sub = db.get(Subscription, payload.subscription_id)
    if not sub:
        raise NotFoundError("Subscription not found")

    existing = (
        db.query(UsageRecord)
        .filter(UsageRecord.subscription_id == sub.id, UsageRecord.usage_date == payload.usage_date)
        .first()
    )
    if existing:
        # Accumulate additional usage recorded for the same day instead of overwriting.
        existing.data_used_mb += payload.data_used_mb
        existing.voice_used_minutes += payload.voice_used_minutes
        existing.sms_used_count += payload.sms_used_count
        db.commit()
        db.refresh(existing)
        return existing

    record = UsageRecord(
        subscription_id=sub.id,
        sim_id=sub.sim_id,
        usage_date=payload.usage_date,
        data_used_mb=payload.data_used_mb,
        voice_used_minutes=payload.voice_used_minutes,
        sms_used_count=payload.sms_used_count,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _percent(used: float, limit: int | None) -> float | None:
    if limit is None or limit == 0:
        return None
    return round(min(used / limit, 999.9) * 100, 2)


def get_subscription_usage_summary(
    db: Session, subscription_id: str, period_start: date_type, period_end: date_type
) -> UsageSummary:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise NotFoundError("Subscription not found")
    plan = db.get(ServicePlan, sub.plan_id)

    totals = (
        db.query(
            func.coalesce(func.sum(UsageRecord.data_used_mb), 0.0),
            func.coalesce(func.sum(UsageRecord.voice_used_minutes), 0.0),
            func.coalesce(func.sum(UsageRecord.sms_used_count), 0),
        )
        .filter(
            UsageRecord.subscription_id == subscription_id,
            UsageRecord.usage_date >= period_start,
            UsageRecord.usage_date <= period_end,
        )
        .first()
    )
    data_used, voice_used, sms_used = totals

    return UsageSummary(
        subscription_id=subscription_id,
        plan_id=plan.id,
        period_start=period_start,
        period_end=period_end,
        total_data_used_mb=data_used,
        total_voice_used_minutes=voice_used,
        total_sms_used_count=sms_used,
        data_limit_mb=plan.data_limit_mb,
        voice_limit_minutes=plan.voice_limit_minutes,
        sms_limit_count=plan.sms_limit_count,
        data_usage_percent=_percent(data_used, plan.data_limit_mb),
        voice_usage_percent=_percent(voice_used, plan.voice_limit_minutes),
        sms_usage_percent=_percent(sms_used, plan.sms_limit_count),
        data_remaining_mb=(plan.data_limit_mb - data_used) if plan.data_limit_mb is not None else None,
        voice_remaining_minutes=(plan.voice_limit_minutes - voice_used) if plan.voice_limit_minutes is not None else None,
        sms_remaining_count=(plan.sms_limit_count - sms_used) if plan.sms_limit_count is not None else None,
    )


def get_sim_usage(db: Session, sim_id: str, period_start: date_type, period_end: date_type):
    sim = db.get(SimCard, sim_id)
    if not sim:
        raise NotFoundError("SIM not found")
    return (
        db.query(UsageRecord)
        .filter(UsageRecord.sim_id == sim_id, UsageRecord.usage_date >= period_start, UsageRecord.usage_date <= period_end)
        .order_by(UsageRecord.usage_date)
        .all()
    )


def get_customer_usage(db: Session, customer_id: str, period_start: date_type, period_end: date_type):
    subs = db.query(Subscription).filter(Subscription.customer_id == customer_id).all()
    results = []
    for sub in subs:
        results.append(get_subscription_usage_summary(db, sub.id, period_start, period_end))
    return results


def get_plan_utilization(db: Session, plan_id: str, period_start: date_type, period_end: date_type) -> dict:
    plan = db.get(ServicePlan, plan_id)
    if not plan:
        raise NotFoundError("Plan not found")

    sub_ids = [s.id for s in db.query(Subscription.id).filter(Subscription.plan_id == plan_id).all()]
    if not sub_ids:
        return {"plan_id": plan_id, "subscriber_count": 0, "avg_data_used_mb": 0.0, "avg_voice_used_minutes": 0.0, "avg_sms_used_count": 0.0}

    totals = (
        db.query(
            func.coalesce(func.sum(UsageRecord.data_used_mb), 0.0),
            func.coalesce(func.sum(UsageRecord.voice_used_minutes), 0.0),
            func.coalesce(func.sum(UsageRecord.sms_used_count), 0),
        )
        .filter(
            UsageRecord.subscription_id.in_(sub_ids),
            UsageRecord.usage_date >= period_start,
            UsageRecord.usage_date <= period_end,
        )
        .first()
    )
    data_used, voice_used, sms_used = totals
    n = len(sub_ids)
    return {
        "plan_id": plan_id,
        "subscriber_count": n,
        "avg_data_used_mb": round(data_used / n, 2),
        "avg_voice_used_minutes": round(voice_used / n, 2),
        "avg_sms_used_count": round(sms_used / n, 2),
    }
