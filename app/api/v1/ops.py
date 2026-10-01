from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin_or_ops
from app.db.session import get_db
from app.models.user import User
from app.workers import jobs

router = APIRouter(prefix="/ops", tags=["Operations Jobs"])


@router.post("/run-jobs")
def run_scheduled_jobs(current_user: User = Depends(require_admin_or_ops), db: Session = Depends(get_db)):
    """Runs the scheduled maintenance jobs once: auto-renew/expire subscriptions, plan-expiry and
    maintenance notifications, and SLA-breach flagging. In production trigger these from cron/Celery beat."""
    return jobs.run_all_jobs(db)
