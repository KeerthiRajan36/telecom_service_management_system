from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin_or_ops
from app.db.session import get_db
from app.models.user import User
from app.models.plan import ServicePlan
from app.models.enums import PlanType, PlanCategory, PlanStatus
from app.schemas.plan import PlanCreate, PlanUpdate, PlanOut, PlanCompareRequest
from app.schemas.common import PaginatedResponse
from app.services import plan_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/plans", tags=["Service Plans"])


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return plan_service.create_plan(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[PlanOut])
def list_plans(
    plan_type: PlanType | None = None,
    category: PlanCategory | None = None,
    status: PlanStatus | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    query = plan_service.query_plans(db, plan_type, category, status, min_price, max_price)
    return paginate(query, params, PlanOut, ServicePlan, search_fields=["name", "code", "description"])


@router.post("/compare", response_model=list[PlanOut])
def compare_plans(payload: PlanCompareRequest, db: Session = Depends(get_db)):
    return plan_service.compare_plans(db, payload.plan_ids)


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: str, db: Session = Depends(get_db)):
    return plan_service.get_plan(db, plan_id)


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: str, payload: PlanUpdate, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return plan_service.update_plan(db, current_user.id, plan_id, payload)


@router.patch("/{plan_id}/status", response_model=PlanOut)
def set_plan_status(plan_id: str, plan_status: PlanStatus, current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    return plan_service.set_plan_status(db, current_user.id, plan_id, plan_status)
