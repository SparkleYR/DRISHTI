from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata owned by the local FastAPI service."""


class Hazard(Base):
    __tablename__ = "hazards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    map_id: Mapped[str | None] = mapped_column(String(96))
    map_version: Mapped[str | None] = mapped_column(String(64))
    map_x: Mapped[float | None] = mapped_column(Float)
    map_y: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confirmation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    temporary: Mapped[bool] = mapped_column(Boolean, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(96))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evidence_path: Mapped[str | None] = mapped_column(Text)
    merged_into_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hazards.id")
    )


class HazardObservation(Base):
    __tablename__ = "hazard_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hazard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hazards.id"), nullable=False, index=True
    )
    source_hazard_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)


class HazardStatusHistory(Base):
    __tablename__ = "hazard_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hazard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hazards.id"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operator_alias: Mapped[str] = mapped_column(String(96), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class AccessibilityRoute(Base):
    __tablename__ = "accessibility_routes"
    __table_args__ = (
        UniqueConstraint("route_key", "specification_version", name="uq_route_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_key: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    map_id: Mapped[str] = mapped_column(String(96), nullable=False)
    map_version: Mapped[str] = mapped_column(String(64), nullable=False)
    specification_version: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AccessibilitySegment(Base):
    __tablename__ = "accessibility_segments"
    __table_args__ = (
        UniqueConstraint("route_id", "segment_key", name="uq_route_segment"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    route_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("accessibility_routes.id"), nullable=False, index=True
    )
    segment_key: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_x: Mapped[float] = mapped_column(Float, nullable=False)
    start_y: Mapped[float] = mapped_column(Float, nullable=False)
    end_x: Mapped[float] = mapped_column(Float, nullable=False)
    end_y: Mapped[float] = mapped_column(Float, nullable=False)
    corridor_radius: Mapped[float] = mapped_column(Float, nullable=False)
