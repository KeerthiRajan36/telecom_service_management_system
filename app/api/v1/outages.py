import math

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import require_network_staff, require_staff
from app.db.session import get_db
from app.models.user import User
from app.models.outage import Outage
from app.models.enums import OutageStatus, OutageSeverity
from app.schemas.outage import OutageCreate, OutageResolve, OutageOut, AffectedCustomerOut
from app.schemas.common import PaginatedResponse
from app.services import outage_service, notification_service
from app.utils.pagination import PageParams, apply_search, apply_sort

router = APIRouter(prefix="/outages", tags=["Network Outages"])


def _to_out(outage: Outage) -> OutageOut:
    return OutageOut(
        id=outage.id,
        title=outage.title,
        description=outage.description,
        outage_type=outage.outage_type,
        severity=outage.severity,
        status=outage.status,
        start_time=outage.start_time,
        expected_resolution=outage.expected_resolution,
        actual_resolution=outage.actual_resolution,
        tower_ids=[t.id for t in outage.towers],
    )


@router.post("", response_model=OutageOut, status_code=status.HTTP_201_CREATED)
def create_outage(
    payload: OutageCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_network_staff),
    db: Session = Depends(get_db),
):
    outage = outage_service.create_outage(db, current_user.id, payload)
    affected = outage_service.get_affected_customers(db, outage.id)
    customer_ids = [a.customer_id for a in affected]
    if customer_ids:
        background_tasks.add_task(notification_service.notify_network_outage, outage.id, customer_ids)
    return _to_out(outage)


@router.get("", response_model=PaginatedResponse[OutageOut])
def list_outages(
    outage_status: OutageStatus | None = None,
    severity: OutageSeverity | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = outage_service.query_outages(db, outage_status, severity)
    # Manual pagination because tower_ids is derived from a relationship.
    query = apply_search(query, Outage, params.search, ["title", "description"])
    query = apply_sort(query, Outage, params.sort_by, params.sort_order)
    total = query.count()
    rows = query.offset((params.page - 1) * params.page_size).limit(params.page_size).all()
    return PaginatedResponse[OutageOut](
        items=[_to_out(o) for o in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=math.ceil(total / params.page_size) if params.page_size else 0,
    )


@router.get("/{outage_id}", response_model=OutageOut)
def get_outage(outage_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return _to_out(outage_service.get_outage(db, outage_id))


@router.get("/{outage_id}/affected-customers", response_model=list[AffectedCustomerOut])
def affected_customers(outage_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return outage_service.get_affected_customers(db, outage_id)


@router.post("/{outage_id}/in-progress", response_model=OutageOut)
def mark_in_progress(outage_id: str, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    return _to_out(outage_service.mark_in_progress(db, current_user.id, outage_id))


@router.post("/{outage_id}/resolve", response_model=OutageOut)
def resolve_outage(
    outage_id: str,
    payload: OutageResolve,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_network_staff),
    db: Session = Depends(get_db),
):
    outage = outage_service.resolve_outage(db, current_user.id, outage_id, payload)
    affected = outage_service.get_affected_customers(db, outage.id)
    customer_ids = [a.customer_id for a in affected]
    if customer_ids:
        background_tasks.add_task(notification_service.notify_service_restoration, outage.id, customer_ids)
    return _to_out(outage)
