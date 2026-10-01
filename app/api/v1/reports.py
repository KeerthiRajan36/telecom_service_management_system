from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin_or_ops
from app.db.session import get_db
from app.models.user import User
from app.models.enums import OutageSeverity, TicketStatus, TicketCategory
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Advanced Reports"])

# Reports are restricted to admins and operations managers.


@router.get("/customer-growth")
def customer_growth(start: date | None = None, end: date | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.customer_growth_report(db, start, end)


@router.get("/subscription-trends")
def subscription_trends(start: date | None = None, end: date | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.subscription_trends_report(db, start, end)


@router.get("/plan-popularity")
def plan_popularity(plan_id: str | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.plan_popularity_report(db, plan_id)


@router.get("/data-consumption")
def data_consumption(
    start: date | None = None,
    end: date | None = None,
    customer_id: str | None = None,
    plan_id: str | None = None,
    current_user: User = Depends(require_admin_or_ops),
    db: Session = Depends(get_db),
):
    return report_service.data_consumption_report(db, start, end, customer_id, plan_id)


@router.get("/network-uptime")
def network_uptime(location: str | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.network_uptime_report(db, location)


@router.get("/outage-frequency")
def outage_frequency(start: date | None = None, end: date | None = None, severity: OutageSeverity | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.outage_frequency_report(db, start, end, severity)


@router.get("/ticket-resolution-time")
def ticket_resolution_time(start: date | None = None, end: date | None = None, ticket_status: TicketStatus | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.ticket_resolution_time_report(db, start, end, ticket_status)


@router.get("/sla-performance")
def sla_performance(start: date | None = None, end: date | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.sla_performance_report(db, start, end)


@router.get("/technician-performance")
def technician_performance(technician_id: str | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.technician_performance_report(db, technician_id)


@router.get("/customer-service-trends")
def customer_service_trends(start: date | None = None, end: date | None = None, category: TicketCategory | None = None, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return report_service.customer_service_trends_report(db, start, end, category)
