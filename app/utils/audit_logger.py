"""Helper to write an AuditLog row. Called from services after state-changing actions."""
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def _safe_json(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return str(value)


def record_audit(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    entity: str,
    entity_id: str | None,
    previous_value: Any = None,
    new_value: Any = None,
    ip_address: str | None = None,
    commit: bool = True,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        previous_value=_safe_json(previous_value),
        new_value=_safe_json(new_value),
        ip_address=ip_address,
    )
    db.add(log)
    if commit:
        db.flush()
    return log
