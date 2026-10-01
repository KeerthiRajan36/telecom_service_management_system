from fastapi import APIRouter

from app.api.v1 import (
    auth, customers, plans, sims, devices, subscriptions, usage,
    towers, equipment, outages, technicians, tickets, sla,
    service_requests, notifications, dashboard, reports, audit, ops,
)

api_router = APIRouter()
for module in (
    auth, customers, plans, sims, devices, subscriptions, usage,
    towers, equipment, outages, technicians, tickets, sla,
    service_requests, notifications, dashboard, reports, audit, ops,
):
    api_router.include_router(module.router)
