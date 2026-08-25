from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.models.vehicle import Vehicle
from backend.app.schemas.vehicle import VehicleCreate, VehicleResponse

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.post("/", response_model=VehicleResponse, status_code=201)
def create_vehicle(
    vehicle_data: VehicleCreate,
    db: Session = Depends(get_db),
):
    existing_registration = db.scalar(
        select(Vehicle).where(
            Vehicle.registration_number == vehicle_data.registration_number
        )
    )

    if existing_registration:
        raise HTTPException(
            status_code=409,
            detail="Registration number already exists",
        )

    existing_chassis = db.scalar(
        select(Vehicle).where(
            Vehicle.chassis_number == vehicle_data.chassis_number
        )
    )

    if existing_chassis:
        raise HTTPException(
            status_code=409,
            detail="Chassis number already exists",
        )

    vehicle = Vehicle(**vehicle_data.model_dump())

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    return vehicle


@router.get("/", response_model=list[VehicleResponse])
def list_vehicles(
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Vehicle).order_by(Vehicle.id)
    ).all()


@router.get("/{vehicle_id}", response_model=VehicleResponse)
def get_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
):
    vehicle = db.get(Vehicle, vehicle_id)

    if vehicle is None:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found",
        )

    return vehicle
