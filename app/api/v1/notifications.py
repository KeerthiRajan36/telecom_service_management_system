from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.notification import Notification
from app.models.enums import UserRole
from app.schemas.notification import NotificationOut
from app.schemas.common import PaginatedResponse
from app.services import notification_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedResponse[NotificationOut])
def my_notifications(
    unread_only: bool = False,
    params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customers see notifications addressed to their customer profile; staff see ones addressed to them."""
    if current_user.role == UserRole.CUSTOMER:
        query = notification_service.list_notifications(db, customer_id=current_user.customer_id, unread_only=unread_only)
    else:
        query = notification_service.list_notifications(db, user_id=current_user.id, unread_only=unread_only)
    return paginate(query, params, NotificationOut)


@router.get("/all", response_model=PaginatedResponse[NotificationOut])
def all_notifications(
    customer_id: str | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Staff-only view of generated notifications (optionally for one customer). Used for demo verification."""
    if current_user.role == UserRole.CUSTOMER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff only")
    query = notification_service.list_notifications(db, customer_id=customer_id)
    if customer_id is None:
        query = db.query(Notification).order_by(Notification.created_at.desc())
    return paginate(query, params, NotificationOut)


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.get(Notification, notification_id)
    if note is not None:
        owns = note.recipient_user_id == current_user.id or (
            current_user.customer_id is not None and note.recipient_customer_id == current_user.customer_id
        )
        if not owns and current_user.role == UserRole.CUSTOMER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only modify your own notifications")
    return notification_service.mark_read(db, notification_id)
