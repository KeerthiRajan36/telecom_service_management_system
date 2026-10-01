from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.subscription import Subscription
from app.models.sim import SimCard
from app.models.usage import UsageRecord
from app.models.outage import Outage
from app.models.ticket import Ticket
from app.models.sla import SLATracking
from app.models.technician import TechnicianAssignment
from app.models.network import Tower
from app.models.service_request import ServiceRequest
from app.models.plan import ServicePlan
from app.models.enums import (
    SubscriptionStatus,
    SimStatus,
    OutageStatus,
    TicketStatus,
    AssignmentStatus,
    TowerStatus,
    ServiceRequestStatus,
    PlanStatus,
)
from app.schemas.dashboard import OperationsDashboard
from app.services import usage_service


def get_operations_dashboard(db: Session) -> OperationsDashboard:
    total_customers = db.query(Customer).filter(Customer.is_deleted.is_(False)).count()
    active_customers = db.query(Customer).filter(Customer.is_deleted.is_(False), Customer.is_active.is_(True)).count()
    active_subscriptions = db.query(Subscription).filter(Subscription.status == SubscriptionStatus.ACTIVE).count()
    active_sims = db.query(SimCard).filter(SimCard.status == SimStatus.ACTIVE).count()

    total_data_usage_mb = db.query(func.coalesce(func.sum(UsageRecord.data_used_mb), 0.0)).scalar()

    open_outages = db.query(Outage).filter(Outage.status != OutageStatus.RESOLVED).count()
    open_tickets = db.query(Ticket).filter(Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED])).count()

    from app.services.sla_service import get_breached_tickets
    sla_breaches = len(get_breached_tickets(db))

    pending_jobs_total = db.query(TechnicianAssignment).filter(
        TechnicianAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS])
    ).count()

    towers_active = db.query(Tower).filter(Tower.status == TowerStatus.ACTIVE).count()
    towers_offline = db.query(Tower).filter(Tower.status == TowerStatus.OFFLINE).count()

    pending_requests = db.query(ServiceRequest).filter(
        ServiceRequest.status.in_([ServiceRequestStatus.SUBMITTED, ServiceRequestStatus.IN_PROGRESS])
    ).count()

    plan_utilization = []
    today = date.today()
    period_start = today.replace(day=1)
    for plan in db.query(ServicePlan).filter(ServicePlan.status == PlanStatus.ACTIVE).limit(10).all():
        plan_utilization.append(usage_service.get_plan_utilization(db, plan.id, period_start, today))

    return OperationsDashboard(
        total_customers=total_customers,
        active_customers=active_customers,
        active_subscriptions=active_subscriptions,
        active_sims=active_sims,
        total_data_usage_mb=total_data_usage_mb,
        open_network_outages=open_outages,
        open_tickets=open_tickets,
        sla_breaches=sla_breaches,
        technician_workload_total_pending=pending_jobs_total,
        towers_active=towers_active,
        towers_offline=towers_offline,
        pending_service_requests=pending_requests,
        plan_utilization=plan_utilization,
    )
