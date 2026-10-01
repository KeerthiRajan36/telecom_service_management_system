from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import require_network_staff, require_staff
from app.db.session import get_db
from app.models.user import User
from app.models.network import NetworkEquipment
from app.models.enums import EquipmentStatus
from app.schemas.network import EquipmentCreate, EquipmentHeartbeat, EquipmentOut
from app.schemas.common import PaginatedResponse
from app.services import network_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/equipment", tags=["Network Equipment"])


@router.post("", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def create_equipment(payload: EquipmentCreate, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    return network_service.create_equipment(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[EquipmentOut])
def list_equipment(
    tower_id: str | None = None,
    equipment_status: EquipmentStatus | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = network_service.query_equipment(db, tower_id, equipment_status)
    return paginate(query, params, EquipmentOut, NetworkEquipment, search_fields=["name"])


@router.get("/stale", response_model=list[EquipmentOut])
def stale_equipment(stale_after_minutes: int = 15, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    """Equipment with no recent heartbeat (likely down)."""
    return network_service.get_stale_equipment(db, stale_after_minutes)


@router.get("/{equipment_id}", response_model=EquipmentOut)
def get_equipment(equipment_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return network_service.get_equipment(db, equipment_id)


@router.post("/{equipment_id}/heartbeat", response_model=EquipmentOut)
def heartbeat(equipment_id: str, payload: EquipmentHeartbeat, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    return network_service.record_heartbeat(db, equipment_id, payload)
