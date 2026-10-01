from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, require_support_staff, assert_customer_access
from app.db.session import get_db
from app.models.user import User
from app.models.subscription import Subscription
from app.models.enums import SubscriptionStatus
from app.schemas.subscription import SubscriptionCreate, SubscriptionPlanChange, SubscriptionOut, SubscriptionHistoryOut
from app.schemas.common import PaginatedResponse
from app.services import subscription_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(payload: SubscriptionCreate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return subscription_service.create_subscription(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[SubscriptionOut])
def list_subscriptions(
    customer_id: str | None = None,
    sub_status: SubscriptionStatus | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = subscription_service.query_subscriptions(db, customer_id, sub_status)
    return paginate(query, params, SubscriptionOut, Subscription)


@router.get("/{subscription_id}", response_model=SubscriptionOut)
def get_subscription(subscription_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = subscription_service.get_subscription(db, subscription_id)
    assert_customer_access(current_user, sub.customer_id)
    return sub


@router.post("/{subscription_id}/change-plan", response_model=SubscriptionOut)
def change_plan(subscription_id: str, payload: SubscriptionPlanChange, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    """Upgrade or downgrade is determined automatically by comparing plan prices."""
    return subscription_service.change_plan(db, current_user.id, subscription_id, payload.new_plan_id, payload.notes)


@router.post("/{subscription_id}/renew", response_model=SubscriptionOut)
def renew(subscription_id: str, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return subscription_service.renew_subscription(db, current_user.id, subscription_id)


@router.post("/{subscription_id}/suspend", response_model=SubscriptionOut)
def suspend(subscription_id: str, notes: str | None = None, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return subscription_service.suspend_subscription(db, current_user.id, subscription_id, notes)


@router.post("/{subscription_id}/reactivate", response_model=SubscriptionOut)
def reactivate(subscription_id: str, notes: str | None = None, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return subscription_service.reactivate_subscription(db, current_user.id, subscription_id, notes)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionOut)
def cancel(subscription_id: str, notes: str | None = None, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return subscription_service.cancel_subscription(db, current_user.id, subscription_id, notes)


@router.get("/{subscription_id}/history", response_model=list[SubscriptionHistoryOut])
def history(subscription_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return subscription_service.get_history(db, subscription_id)
