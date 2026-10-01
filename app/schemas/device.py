from pydantic import BaseModel

from app.models.enums import DeviceType, DeviceStatus
from app.schemas.common import ORMModel


class DeviceCreate(BaseModel):
    imei: str
    model: str
    manufacturer: str
    device_type: DeviceType = DeviceType.SMARTPHONE
    customer_id: str | None = None
    sim_id: str | None = None


class DeviceUpdate(BaseModel):
    model: str | None = None
    manufacturer: str | None = None
    device_type: DeviceType | None = None
    status: DeviceStatus | None = None


class DeviceAssignSim(BaseModel):
    sim_id: str


class DeviceOut(ORMModel):
    id: str
    imei: str
    model: str
    manufacturer: str
    device_type: DeviceType
    status: DeviceStatus
    customer_id: str | None
    sim_id: str | None
