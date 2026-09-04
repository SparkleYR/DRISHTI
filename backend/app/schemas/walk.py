from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, SCHEMA_VERSION


Normalized = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
NonNegativeMilliseconds = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]


class WalkSettings(ApiModel):
    speech_rate: Normalized | None = None
    preferred_language: Annotated[str, Field(min_length=2, max_length=35)] | None = None
    haptics_enabled: bool | None = None
    risk_sensitivity: Normalized | None = None


class StartWalkSessionRequest(ApiModel):
    device_alias: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    settings: WalkSettings | None = None


class StartWalkSessionResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    session_id: str
    started_at: datetime
    recommended_capture_fps: Annotated[float, Field(gt=0)]
    max_image_width: Annotated[int, Field(gt=0)]
    max_image_bytes: Annotated[int, Field(gt=0)]
    max_result_age_ms: Annotated[int, Field(gt=0)]


class EndWalkSessionResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    session_id: str
    ended_at: datetime
    status: Literal["ENDED"] = "ENDED"


class CoordinateSpace(StrEnum):
    ORIENTED_CAPTURE_NORMALIZED = "ORIENTED_CAPTURE_NORMALIZED"


class RotationDegrees(IntEnum):
    DEG_0 = 0
    DEG_90 = 90
    DEG_180 = 180
    DEG_270 = 270


class CorridorChoice(StrEnum):
    LEFT = "LEFT"
    CENTRE = "CENTRE"
    RIGHT = "RIGHT"
    NONE = "NONE"


class DirectionArrow(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    STOP = "STOP"
    NONE = "NONE"


class RiskLevel(StrEnum):
    CLEAR = "CLEAR"
    WATCH = "WATCH"
    WARN = "WARN"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Direction(StrEnum):
    LEFT = "LEFT"
    CENTRE = "CENTRE"
    RIGHT = "RIGHT"
    UNKNOWN = "UNKNOWN"


class ProximityBand(StrEnum):
    FAR = "FAR"
    MEDIUM = "MEDIUM"
    NEAR = "NEAR"
    IMMEDIATE = "IMMEDIATE"
    UNKNOWN = "UNKNOWN"


class ApproachState(StrEnum):
    APPROACHING = "APPROACHING"
    RECEDING = "RECEDING"
    STATIONARY = "STATIONARY"
    UNKNOWN = "UNKNOWN"


class DisplayColor(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    GREY = "GREY"


class SurfaceKind(StrEnum):
    WALKABLE = "WALKABLE"
    ROAD = "ROAD"
    NON_WALKABLE = "NON_WALKABLE"
    UNKNOWN = "UNKNOWN"


class GuidanceAction(StrEnum):
    CLEAR = "CLEAR"
    CAUTION = "CAUTION"
    MOVE_LEFT = "MOVE_LEFT"
    MOVE_RIGHT = "MOVE_RIGHT"
    STOP = "STOP"
    PAUSE_UNCLEAR = "PAUSE_UNCLEAR"


class HapticPattern(StrEnum):
    NONE = "NONE"
    CAUTION_SHORT = "CAUTION_SHORT"
    WARNING_DOUBLE = "WARNING_DOUBLE"
    CRITICAL_RAPID = "CRITICAL_RAPID"
    UNCLEAR_LONG = "UNCLEAR_LONG"


class TargetTrackingState(StrEnum):
    IDLE = "IDLE"
    SEEKING = "SEEKING"
    GUIDING = "GUIDING"
    ARRIVED = "ARRIVED"
    LOST = "LOST"


class TargetGuidanceStep(StrEnum):
    NONE = "NONE"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    KEEP_TURNING = "KEEP_TURNING"
    FACE_AND_WALK = "FACE_AND_WALK"
    WALKING = "WALKING"
    ARRIVED = "ARRIVED"
    REACQUIRE = "REACQUIRE"


class TargetRangeHint(StrEnum):
    NEAR = "NEAR"
    MID = "MID"
    FAR = "FAR"
    UNKNOWN = "UNKNOWN"


class TargetHapticPattern(StrEnum):
    NONE = "NONE"
    TARGET_LEFT_PULSE = "TARGET_LEFT_PULSE"
    TARGET_CENTRE_PULSE = "TARGET_CENTRE_PULSE"
    TARGET_RIGHT_PULSE = "TARGET_RIGHT_PULSE"


class NormalizedPoint(ApiModel):
    x: Normalized
    y: Normalized


class NormalizedBoundingBox(ApiModel):
    x1: Normalized
    y1: Normalized
    x2: Normalized
    y2: Normalized

    @model_validator(mode="after")
    def validate_order(self) -> "NormalizedBoundingBox":
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("bounding-box minimums must be below maximums")
        return self


NormalizedPolygon = Annotated[list[NormalizedPoint], Field(min_length=3, max_length=64)]
PolygonCollection = Annotated[list[NormalizedPolygon], Field(max_length=16)]


class MotionVector(ApiModel):
    dx: FiniteNumber
    dy: FiniteNumber


class DetectionResult(ApiModel):
    track_id: Annotated[int, Field(ge=0)] | None = None
    label: Annotated[str, Field(min_length=1)]
    confidence: Normalized
    bbox: NormalizedBoundingBox
    anchor: NormalizedPoint
    direction: Direction
    proximity: ProximityBand
    proximity_score: Normalized | None = None
    approach_state: ApproachState
    approach_rate: Normalized | None = None
    motion_vector: MotionVector | None = None
    path_overlap: Normalized
    risk_score: Normalized
    risk_level: RiskLevel
    display_color: DisplayColor


class SurfaceRegion(ApiModel):
    kind: SurfaceKind
    confidence: Normalized
    polygon: NormalizedPolygon
    source_frame_id: Annotated[int, Field(ge=0)]


class FrameGeometry(ApiModel):
    coordinate_space: Literal["ORIENTED_CAPTURE_NORMALIZED"] = (
        CoordinateSpace.ORIENTED_CAPTURE_NORMALIZED
    )
    source_width: Annotated[int, Field(gt=0)]
    source_height: Annotated[int, Field(gt=0)]
    rotation_degrees: Literal[0, 90, 180, 270]
    mirrored: Literal[False] = False


class CorridorCosts(ApiModel):
    left_cost: Normalized
    centre_cost: Normalized
    right_cost: Normalized


class OverlayContract(ApiModel):
    coordinate_space: Literal["ORIENTED_CAPTURE_NORMALIZED"] = (
        CoordinateSpace.ORIENTED_CAPTURE_NORMALIZED
    )
    preferred_corridor: CorridorChoice
    safe_polygons: PolygonCollection
    blocked_polygons: PolygonCollection
    uncertain_polygons: PolygonCollection
    direction_arrow: DirectionArrow
    valid_until: datetime


class GuidanceContract(ApiModel):
    level: RiskLevel
    action: GuidanceAction
    speech: str
    haptic_pattern: HapticPattern
    speak: bool
    reason_code: str


class TargetTrackingTelemetry(ApiModel):
    tracking_state: TargetTrackingState
    target_name: str | None = None
    guidance_step: TargetGuidanceStep = TargetGuidanceStep.NONE
    bearing_degrees: FiniteNumber | None = None
    range_hint: TargetRangeHint = TargetRangeHint.UNKNOWN
    # Deprecated compatibility bridge for the native client. New guidance never
    # speaks or derives behavior from this field.
    clock_direction: str | None = None
    target_center: NormalizedPoint | None = None
    confidence: Normalized | None = None
    is_safety_overridden: bool = False
    speech: str = ""
    speak: bool = False
    haptic_pattern: TargetHapticPattern = TargetHapticPattern.NONE


class TargetTelemetryEvent(TargetTrackingTelemetry):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    session_id: str
    frame_id: Annotated[int, Field(ge=0)]


class StageTimings(ApiModel):
    decode_ms: NonNegativeMilliseconds
    detection_ms: NonNegativeMilliseconds | None = None
    segmentation_ms: NonNegativeMilliseconds | None = None
    tracking_depth_ms: NonNegativeMilliseconds | None = None
    spatial_ms: NonNegativeMilliseconds | None = None
    risk_ms: NonNegativeMilliseconds | None = None
    total_ms: NonNegativeMilliseconds


class FrameAnalysisResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    session_id: str
    frame_id: Annotated[int, Field(ge=0)]
    captured_at: datetime
    received_at: datetime
    processed_at: datetime
    frame_age_ms: NonNegativeMilliseconds
    geometry: FrameGeometry
    detections: list[DetectionResult]
    surfaces: list[SurfaceRegion]
    corridors: CorridorCosts
    overlay: OverlayContract
    guidance: GuidanceContract
    target_tracking: TargetTrackingTelemetry
    timings: StageTimings
    degraded_modules: list[str]
