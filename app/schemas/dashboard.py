from pydantic import BaseModel


class OperationsDashboard(BaseModel):
    total_customers: int
    active_customers: int
    active_subscriptions: int
    active_sims: int
    total_data_usage_mb: float
    open_network_outages: int
    open_tickets: int
    sla_breaches: int
    technician_workload_total_pending: int
    towers_active: int
    towers_offline: int
    pending_service_requests: int
    plan_utilization: list[dict]
