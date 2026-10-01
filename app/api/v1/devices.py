from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_staff, require_support_staff, assert_customer_access
from app.db.session import get_db
from app.models.user import User
from app.models.device import Device
from app.models.enums import DeviceStatus
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceAssignSim, DeviceOut
from app.schemas.common import PaginatedResponse
from app.services import device_service
from app.utils.pagination import PageParams, paginate

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return device_service.create_device(db, current_user.id, payload)


@router.get("", response_model=PaginatedResponse[DeviceOut])
def list_devices(
    device_status: DeviceStatus | None = None,
    customer_id: str | None = None,
    params: PageParams = Depends(),
    current_user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = device_service.query_devices(db, device_status, customer_id)
    return paginate(query, params, DeviceOut, Device, search_fields=["imei", "model", "manufacturer"])


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = device_service.get_device(db, device_id)
    assert_customer_access(current_user, device.customer_id)
    return device


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(device_id: str, payload: DeviceUpdate, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return device_service.update_device(db, current_user.id, device_id, payload)


@router.post("/{device_id}/assign-sim", response_model=DeviceOut)
def assign_sim(device_id: str, payload: DeviceAssignSim, current_user: User = Depends(require_support_staff), db: Session = Depends(get_db)):
    return device_service.assign_sim(db, current_user.id, device_id, payload.sim_id)
