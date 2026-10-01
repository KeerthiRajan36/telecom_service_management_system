from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_network_staff, require_staff
from app.db.session import get_db
from app.models.user import User
from app.models.network import Tower
from app.models.enums import TowerStatus
from app.schemas.network import TowerCreate, TowerUpdate, TowerOut
from app.schemas.common import PaginatedResponse
from app.services import network_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/towers", tags=["Network Towers"])


@router.post("", response_model=TowerOut, status_code=status.HTTP_201_CREATED)
def create_tower(payload: TowerCreate, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    return network_service.create_tower(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[TowerOut])
def list_towers(
    tower_status: TowerStatus | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = network_service.query_towers(db, tower_status)
    return paginate(query, params, TowerOut, Tower, search_fields=["code", "name"])


@router.get("/{tower_id}", response_model=TowerOut)
def get_tower(tower_id: str, current_user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return network_service.get_tower(db, tower_id)


@router.patch("/{tower_id}", response_model=TowerOut)
def update_tower(tower_id: str, payload: TowerUpdate, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    return network_service.update_tower(db, current_user.id, tower_id, payload)


@router.patch("/{tower_id}/status", response_model=TowerOut)
def set_tower_status(tower_id: str, tower_status: TowerStatus, current_user: User = Depends(require_network_staff), db: Session = Depends(get_db)):
    return network_service.set_tower_status(db, current_user.id, tower_id, tower_status)
