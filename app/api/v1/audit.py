from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin_or_ops
from app.db.session import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogOut
from app.schemas.common import PaginatedResponse
from app.services import audit_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=PaginatedResponse[AuditLogOut])
def list_audit_logs(
    entity: str | None = None,
    action: str | None = None,
    user_id: str | None = None,
    entity_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_admin_or_ops),
    db: Session = Depends(get_db),
):
    query = audit_service.query_audit_logs(db, entity, action, user_id, entity_id, start, end)
    if not params.sort_by:
        params.sort_by, params.sort_order = "created_at", "desc"
    return paginate(query, params, AuditLogOut, AuditLog, search_fields=["action", "entity"])
