from datetime import datetime

from pydantic import BaseModel

from app.models.enums import NotificationType
from app.schemas.common import ORMModel


class NotificationOut(ORMModel):
    id: str
    notification_type: NotificationType
    title: str
    message: str
    is_read: bool
    created_at: datetime
