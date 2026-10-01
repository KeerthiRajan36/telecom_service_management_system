from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_staff
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import OperationsDashboard
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Operations Dashboard"])


@router.get("/operations", response_model=OperationsDashboard)
def operations_dashboard(current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return dashboard_service.get_operations_dashboard(db)
