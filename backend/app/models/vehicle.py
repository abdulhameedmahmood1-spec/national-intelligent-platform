from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    plate_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    registration_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    chassis_number: Mapped[str] = mapped_column(
        String(17),
        nullable=False,
        unique=True,
        index=True,
    )

    owner_nin_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    owner_department: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    owner_address: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    vehicle_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    make: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    color: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
