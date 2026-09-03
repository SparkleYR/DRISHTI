from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ApiModel, SCHEMA_VERSION
from app.schemas.walk import Direction, Normalized


class HazardSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HazardStatus(StrEnum):
    NEW = "NEW"
    VERIFIED = "VERIFIED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


ACTIVE_HAZARD_STATUSES = (
    HazardStatus.NEW,
    HazardStatus.VERIFIED,
    HazardStatus.ASSIGNED,
    HazardStatus.IN_PROGRESS,
)


class VersionedMapCoordinate(ApiModel):
    map_id: Annotated[str, Field(min_length=1, max_length=96)]
    map_version: Annotated[str, Field(min_length=1, max_length=64)]
    x: Normalized
    y: Normalized


class GeoCoordinate(ApiModel):
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    accuracy_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None


class HazardRecord(ApiModel):
    id: str
    category: str
    severity: HazardSeverity
    status: HazardStatus
    map_coordinate: VersionedMapCoordinate | None = None
    geo_coordinate: GeoCoordinate | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    confidence: Normalized
    confirmation_count: Annotated[int, Field(ge=1)]
    temporary: bool
    assigned_to: str | None = None
    version: Annotated[int, Field(ge=1)]
    has_consented_evidence: bool


class HazardObservation(ApiModel):
    id: str
    hazard_id: str
    session_id: str | None = None
    observed_at: datetime
    confidence: Normalized
    risk_score: Normalized | None = None
    direction: Direction


class CreateHazardRequest(ApiModel):
    session_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    category: Annotated[str, Field(min_length=1, max_length=96)]
    severity: HazardSeverity
    confidence: Normalized
    risk_score: Normalized | None = None
    direction: Direction = Direction.UNKNOWN
    observed_at: datetime
    map_coordinate: VersionedMapCoordinate | None = None
    geo_coordinate: GeoCoordinate | None = None
    temporary: bool
    evidence_consent: bool

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("category cannot be blank")
        return normalized

    @field_validator("observed_at")
    @classmethod
    def require_utc_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a UTC offset")
        return value.astimezone(UTC)


class HazardResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    hazard: HazardRecord
    merged_with_existing: bool


class HazardListResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    items: list[HazardRecord]
    next_cursor: str | None = None


class UpdateHazardStatusRequest(ApiModel):
    expected_version: Annotated[int, Field(ge=1)]
    expected_status: HazardStatus
    new_status: HazardStatus
    operator_alias: Annotated[str, Field(min_length=1, max_length=96)]
    assigned_to: Annotated[str, Field(min_length=1, max_length=96)] | None = None
    note: Annotated[str, Field(max_length=1000)] | None = None

    @field_validator("operator_alias", "assigned_to", "note")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_operator(self) -> "UpdateHazardStatusRequest":
        if self.operator_alias is None:
            raise ValueError("operator_alias cannot be blank")
        return self


class HazardStatusHistoryRecord(ApiModel):
    id: str
    hazard_id: str
    from_status: HazardStatus
    to_status: HazardStatus
    changed_at: datetime
    operator_alias: str
    note: str | None = None


class UpdateHazardStatusResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    hazard: HazardRecord
    transition: HazardStatusHistoryRecord


class MergeHazardRequest(ApiModel):
    duplicate_hazard_id: Annotated[str, Field(min_length=1)]
    expected_primary_version: Annotated[int, Field(ge=1)]
    expected_duplicate_version: Annotated[int, Field(ge=1)]
    operator_alias: Annotated[str, Field(min_length=1, max_length=96)]
    note: Annotated[str, Field(max_length=1000)] | None = None

    @field_validator("operator_alias", "note")
    @classmethod
    def strip_merge_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_merge_operator(self) -> "MergeHazardRequest":
        if self.operator_alias is None:
            raise ValueError("operator_alias cannot be blank")
        return self


class MergeHazardResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    primary_hazard: HazardRecord
    merged_hazard_id: str


class DashboardCounts(ApiModel):
    new: Annotated[int, Field(ge=0)]
    verified: Annotated[int, Field(ge=0)]
    assigned: Annotated[int, Field(ge=0)]
    in_progress: Annotated[int, Field(ge=0)]
    resolved: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]


class DashboardSummaryResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    counts: DashboardCounts
    active_verified_hazards: Annotated[int, Field(ge=0)]
    awaiting_review: Annotated[int, Field(ge=0)]
    recently_resolved: list[HazardRecord]
    median_resolution_minutes: Annotated[
        float, Field(ge=0, allow_inf_nan=False)
    ] | None = None


class AccessibilityBand(StrEnum):
    HIGH_ACCESS = "HIGH_ACCESS"
    MODERATE_ACCESS = "MODERATE_ACCESS"
    LOW_ACCESS = "LOW_ACCESS"
    SEVERELY_OBSTRUCTED = "SEVERELY_OBSTRUCTED"


class RouteSegmentRecord(ApiModel):
    id: str
    segment_key: str
    name: str
    sequence: Annotated[int, Field(ge=1)]
    start: VersionedMapCoordinate
    end: VersionedMapCoordinate
    corridor_radius: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]


class AccessibilityFactor(ApiModel):
    hazard_id: str
    category: str
    severity: HazardSeverity
    status: HazardStatus
    confirmation_count: Annotated[int, Field(ge=1)]
    confidence: Normalized
    temporary: bool
    age_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    distance_to_segment: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    severity_points: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    status_factor: Normalized
    recurrence_factor: Annotated[float, Field(ge=1, le=1.5, allow_inf_nan=False)]
    confidence_factor: Normalized
    freshness_factor: Normalized
    spatial_factor: Normalized
    penalty_points: Annotated[float, Field(ge=0, le=60, allow_inf_nan=False)]
    explanation: str


class SegmentAccessibilityScore(ApiModel):
    segment: RouteSegmentRecord
    score: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    band: AccessibilityBand
    factors: list[AccessibilityFactor]


class RouteAccessibilityScore(ApiModel):
    route_id: str
    route_key: str
    route_name: str
    description: str
    map_id: str
    map_version: str
    specification_version: str
    score: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    band: AccessibilityBand
    active_hazard_count: Annotated[int, Field(ge=0)]
    recurring_hazard_count: Annotated[int, Field(ge=0)]
    segments: list[SegmentAccessibilityScore]


class DashboardAccessibilityResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    advisory_only: Literal[True] = True
    disclaimer: str
    expired_temporary_count: Annotated[int, Field(ge=0)]
    routes: list[RouteAccessibilityScore]
