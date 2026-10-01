from datetime import date

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def query_audit_logs(
    db: Session,
    entity: str | None = None,
    action: str | None = None,
    user_id: str | None = None,
    entity_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
):
    query = db.query(AuditLog)
    if entity:
        query = query.filter(AuditLog.entity == entity)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    return query
