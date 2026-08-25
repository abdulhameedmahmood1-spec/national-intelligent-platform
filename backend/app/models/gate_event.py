from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.database import Base


class GateEvent(Base):
    __tablename__ = "gate_events"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id"),
        nullable=True,
        index=True,
    )

    detected_plate_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    plate_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    vehicle_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    camera_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    gate_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    decision: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="CHECK",
        index=True,
    )

    decision_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    hardware_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        index=True,
    )

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
