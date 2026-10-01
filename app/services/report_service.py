"""
Advanced reports (Level 18). Grouping is done in Python rather than with
DB-specific date-trunc functions so the same code works unchanged on SQLite,
Postgres or MySQL.
"""
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.subscription import Subscription, SubscriptionHistory
from app.models.plan import ServicePlan
from app.models.usage import UsageRecord
from app.models.network import Tower
from app.models.outage import Outage
from app.models.ticket import Ticket
from app.models.sla import SLATracking
from app.models.technician import TechnicianAssignment
from app.models.enums import OutageStatus, TicketStatus, AssignmentStatus


def _month_key(dt: datetime | date) -> str:
    return dt.strftime("%Y-%m")


def _in_range(dt, start, end) -> bool:
    d = dt.date() if isinstance(dt, datetime) else dt
    return (start is None or d >= start) and (end is None or d <= end)


def customer_growth_report(db: Session, start: date | None = None, end: date | None = None):
    customers = db.query(Customer).all()
    buckets: dict[str, int] = defaultdict(int)
    for c in customers:
        if _in_range(c.created_at, start, end):
            buckets[_month_key(c.created_at)] += 1
    return [{"month": k, "new_customers": v} for k, v in sorted(buckets.items())]


def subscription_trends_report(db: Session, start: date | None = None, end: date | None = None):
    rows = db.query(SubscriptionHistory).all()
    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        if _in_range(r.created_at, start, end):
            buckets[(_month_key(r.created_at), r.action)] += 1
    result = defaultdict(dict)
    for (month, action), count in buckets.items():
        result[month][action] = count
    return [{"month": m, **actions} for m, actions in sorted(result.items())]


def plan_popularity_report(db: Session, plan_id: str | None = None):
    query = db.query(Subscription.plan_id, ServicePlan.name).join(ServicePlan, ServicePlan.id == Subscription.plan_id)
    if plan_id:
        query = query.filter(Subscription.plan_id == plan_id)
    counts: dict[str, dict] = defaultdict(lambda: {"plan_name": "", "subscriber_count": 0})
    for pid, name in query.all():
        counts[pid]["plan_name"] = name
        counts[pid]["subscriber_count"] += 1
    return [{"plan_id": pid, **data} for pid, data in sorted(counts.items(), key=lambda kv: -kv[1]["subscriber_count"])]


def data_consumption_report(db: Session, start: date | None = None, end: date | None = None, customer_id: str | None = None, plan_id: str | None = None):
    query = db.query(UsageRecord)
    if customer_id:
        sub_ids = [s.id for s in db.query(Subscription.id).filter(Subscription.customer_id == customer_id).all()]
        query = query.filter(UsageRecord.subscription_id.in_(sub_ids))
    if plan_id:
        sub_ids = [s.id for s in db.query(Subscription.id).filter(Subscription.plan_id == plan_id).all()]
        query = query.filter(UsageRecord.subscription_id.in_(sub_ids))

    buckets: dict[str, float] = defaultdict(float)
    for rec in query.all():
        if _in_range(rec.usage_date, start, end):
            buckets[_month_key(rec.usage_date)] += rec.data_used_mb
    return [{"month": k, "total_data_used_mb": round(v, 2)} for k, v in sorted(buckets.items())]


def network_uptime_report(db: Session, location: str | None = None):
    """Approximate uptime % per tower over the last 30 days based on outage duration."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=30)
    window_hours = 30 * 24

    towers = db.query(Tower).all()
    if location:
        towers = [t for t in towers if location.lower() in t.name.lower() or location.lower() in t.code.lower()]

    results = []
    for tower in towers:
        outages = (
            db.query(Outage)
            .join(Outage.towers)
            .filter(Tower.id == tower.id, Outage.start_time >= window_start)
            .all()
        )
        downtime_hours = 0.0
        for o in outages:
            end = o.actual_resolution or now
            start_clamped = max(o.start_time, window_start)
            delta = (end - start_clamped).total_seconds() / 3600
            downtime_hours += max(delta, 0)
        uptime_pct = max(0.0, min(100.0, (1 - downtime_hours / window_hours) * 100))
        results.append({"tower_id": tower.id, "tower_code": tower.code, "uptime_percent": round(uptime_pct, 2)})
    return results


def outage_frequency_report(db: Session, start: date | None = None, end: date | None = None, severity=None):
    query = db.query(Outage)
    if severity:
        query = query.filter(Outage.severity == severity)
    buckets: dict[str, int] = defaultdict(int)
    for o in query.all():
        if _in_range(o.start_time, start, end):
            buckets[_month_key(o.start_time)] += 1
    return [{"month": k, "outage_count": v} for k, v in sorted(buckets.items())]


def ticket_resolution_time_report(db: Session, start: date | None = None, end: date | None = None, status: TicketStatus | None = None):
    query = db.query(Ticket).filter(Ticket.resolved_at.isnot(None))
    if status:
        query = query.filter(Ticket.status == status)
    durations = []
    for t in query.all():
        if _in_range(t.created_at, start, end):
            hours = (t.resolved_at - t.created_at).total_seconds() / 3600
            durations.append(hours)
    if not durations:
        return {"ticket_count": 0, "avg_resolution_hours": 0.0, "min_resolution_hours": 0.0, "max_resolution_hours": 0.0}
    return {
        "ticket_count": len(durations),
        "avg_resolution_hours": round(sum(durations) / len(durations), 2),
        "min_resolution_hours": round(min(durations), 2),
        "max_resolution_hours": round(max(durations), 2),
    }


def sla_performance_report(db: Session, start: date | None = None, end: date | None = None):
    query = db.query(SLATracking)
    total = 0
    breached = 0
    for tr in query.all():
        if _in_range(tr.sla_start_time, start, end):
            total += 1
            if tr.breached:
                breached += 1
    met = total - breached
    return {
        "total_tracked": total,
        "met": met,
        "breached": breached,
        "compliance_percent": round((met / total) * 100, 2) if total else 100.0,
    }


def technician_performance_report(db: Session, technician_id: str | None = None):
    query = db.query(TechnicianAssignment)
    if technician_id:
        query = query.filter(TechnicianAssignment.technician_id == technician_id)

    by_tech: dict[str, dict] = defaultdict(lambda: {"completed": 0, "pending": 0, "in_progress": 0, "total_completion_hours": 0.0, "completed_with_time": 0})
    for a in query.all():
        bucket = by_tech[a.technician_id]
        if a.status == AssignmentStatus.COMPLETED:
            bucket["completed"] += 1
            if a.completed_at:
                bucket["total_completion_hours"] += (a.completed_at - a.assigned_at).total_seconds() / 3600
                bucket["completed_with_time"] += 1
        elif a.status == AssignmentStatus.ASSIGNED:
            bucket["pending"] += 1
        elif a.status == AssignmentStatus.IN_PROGRESS:
            bucket["in_progress"] += 1

    results = []
    for tech_id, b in by_tech.items():
        avg_hours = (b["total_completion_hours"] / b["completed_with_time"]) if b["completed_with_time"] else None
        results.append({
            "technician_id": tech_id,
            "completed_jobs": b["completed"],
            "pending_jobs": b["pending"],
            "in_progress_jobs": b["in_progress"],
            "avg_completion_hours": round(avg_hours, 2) if avg_hours is not None else None,
        })
    return results


def customer_service_trends_report(db: Session, start: date | None = None, end: date | None = None, category=None):
    query = db.query(Ticket)
    if category:
        query = query.filter(Ticket.category == category)
    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for t in query.all():
        if _in_range(t.created_at, start, end):
            buckets[(_month_key(t.created_at), t.category.value)] += 1
    result = defaultdict(dict)
    for (month, cat), count in buckets.items():
        result[month][cat] = count
    return [{"month": m, "by_category": cats} for m, cats in sorted(result.items())]
