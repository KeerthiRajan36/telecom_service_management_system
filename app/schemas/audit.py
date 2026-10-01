from datetime import datetime

from app.schemas.common import ORMModel


class AuditLogOut(ORMModel):
    id: str
    user_id: str | None
    action: str
    entity: str
    entity_id: str | None
    previous_value: str | None
    new_value: str | None
    ip_address: str | None
    created_at: datetime
