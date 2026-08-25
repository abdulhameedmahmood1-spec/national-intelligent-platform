from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VehicleCreate(BaseModel):
    plate_number: str
    registration_number: str
    chassis_number: str
    owner_nin_number: str | None = None
    phone_number: str | None = None
    owner_department: str | None = None
    owner_address: str | None = None
    vehicle_type: str | None = None
    make: str | None = None
    model: str | None = None
    color: str | None = None


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_number: str
    registration_number: str
    chassis_number: str
    owner_nin_number: str | None
    phone_number: str | None
    owner_department: str | None
    owner_address: str | None
    vehicle_type: str | None
    make: str | None
    model: str | None
    color: str | None
    created_at: datetime
    updated_at: datetime
