from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.frame_ingress import JPEG_CONTENT_TYPE, decode_jpeg
from app.guidance.actions import build_guidance
from app.guidance.overlay_contract import build_overlay
from app.perception.detector import Detector
from app.perception.segmenter import SegmentationFrame, Segmenter
from app.perception.tracking import TrackingSessionStore
from app.risk.rules import select_action
from app.risk.scoring import RiskAssessment, score_tracks
from app.risk.state_machine import RiskSessionStore
from app.scheduling.latest_frame import LatestFrameScheduler
from app.schemas.common import utc_now
from app.schemas.walk import (
    DetectionResult,
    DisplayColor,
    EndWalkSessionResponse,
    FrameAnalysisResponse,
    FrameGeometry,
    MotionVector,
    NormalizedBoundingBox,
    NormalizedPoint,
    RiskLevel,
    RotationDegrees,
    StageTimings,
    StartWalkSessionRequest,
    StartWalkSessionResponse,
)
from app.spatial.corridor import analyze_corridors
from app.spatial.surfaces import extract_surface_regions
from app.walk_sessions import WalkSession, WalkSessionStore


router = APIRouter(prefix="/api/v1/walk", tags=["walk"])


@router.post("/sessions", response_model=StartWalkSessionResponse, status_code=201)
def start_walk_session(
    payload: StartWalkSessionRequest,
    request: Request,
) -> StartWalkSessionResponse:
    now = utc_now()
    settings: Settings = request.app.state.settings
    sessions: WalkSessionStore = request.app.state.walk_sessions
    session = sessions.start(payload, now)
    tracking_sessions: TrackingSessionStore = request.app.state.tracking_sessions
    tracking_sessions.start_session(session.session_id)
    risk_sessions: RiskSessionStore = request.app.state.risk_sessions
    risk_sessions.start_session(session.session_id)
    return StartWalkSessionResponse(
        server_time=now,
        session_id=session.session_id,
        started_at=session.started_at,
        recommended_capture_fps=settings.recommended_capture_fps,
        max_image_width=settings.max_image_width,
        max_image_bytes=settings.max_image_bytes,
        max_result_age_ms=settings.max_result_age_ms,
    )


@router.patch("/sessions/{session_id}/end", response_model=EndWalkSessionResponse)
async def end_walk_session(session_id: str, request: Request) -> EndWalkSessionResponse:
    now = utc_now()
    sessions: WalkSessionStore = request.app.state.walk_sessions
    session = sessions.end(session_id, now)
    scheduler: LatestFrameScheduler[FrameAnalysisResponse] = (
        request.app.state.frame_scheduler
    )
    await scheduler.end_session(session_id)
    tracking_sessions: TrackingSessionStore = request.app.state.tracking_sessions
    tracking_sessions.end_session(session_id)
    risk_sessions: RiskSessionStore = request.app.state.risk_sessions
    risk_sessions.end_session(session_id)
    assert session.ended_at is not None
    return EndWalkSessionResponse(
        server_time=now,
        session_id=session.session_id,
        ended_at=session.ended_at,
    )


@router.post("/analyze", response_model=FrameAnalysisResponse)
async def analyze_frame(
    request: Request,
    frame: Annotated[UploadFile, File()],
    session_id: Annotated[str, Form(min_length=1)],
    frame_id: Annotated[int, Form(ge=0)],
    captured_at: Annotated[datetime, Form()],
    rotation_degrees: Annotated[RotationDegrees, Form()],
) -> FrameAnalysisResponse:
    received_at = utc_now()
    started = perf_counter()
    settings: Settings = request.app.state.settings
    sessions: WalkSessionStore = request.app.state.walk_sessions
    session = sessions.require_active(session_id)
    detector: Detector = request.app.state.detector
    if not detector.ready:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local object detector is unavailable. Walk Mode cannot start.",
            status_code=503,
            retryable=True,
            details={"detector": detector.detail},
        )

    captured_at = _require_utc(captured_at)
    frame_age_ms = (received_at - captured_at).total_seconds() * 1000
    if frame_age_ms > settings.max_result_age_ms:
        raise AppError(
            ErrorCode.FRAME_TOO_OLD,
            "The captured frame is too old to analyze.",
            status_code=409,
            retryable=True,
            details={"max_result_age_ms": settings.max_result_age_ms},
        )
    if frame_age_ms < -5_000:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "The capture timestamp is too far in the future.",
            status_code=422,
        )
    sessions.accept_frame_id(session_id, frame_id)

    if frame.content_type != JPEG_CONTENT_TYPE:
        raise AppError(
            ErrorCode.INVALID_CONTENT_TYPE,
            "The frame part must use image/jpeg.",
            status_code=415,
        )
    if getattr(frame.file, "_rolled", False):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "The local in-memory upload boundary was not preserved.",
            status_code=500,
        )

    frame_bytes = await frame.read(settings.max_image_bytes + 1)
    await frame.close()
    if len(frame_bytes) > settings.max_image_bytes:
        raise AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            "The JPEG exceeds the session byte limit.",
            status_code=413,
            details={"max_image_bytes": settings.max_image_bytes},
        )

    scheduler: LatestFrameScheduler[FrameAnalysisResponse] = (
        request.app.state.frame_scheduler
    )
    return await scheduler.submit(
        session_id,
        frame_id,
        lambda: _process_accepted_frame(
            request=request,
            session=session,
            frame_bytes=frame_bytes,
            session_id=session_id,
            frame_id=frame_id,
            captured_at=captured_at,
            rotation_degrees=rotation_degrees,
            received_at=received_at,
            request_started=started,
        ),
    )


async def _process_accepted_frame(
    *,
    request: Request,
    session: WalkSession,
    frame_bytes: bytes,
    session_id: str,
    frame_id: int,
    captured_at: datetime,
    rotation_degrees: RotationDegrees,
    received_at: datetime,
    request_started: float,
) -> FrameAnalysisResponse:
    settings: Settings = request.app.state.settings
    detector: Detector = request.app.state.detector
    queued_age_ms = (utc_now() - captured_at).total_seconds() * 1000
    if queued_age_ms > settings.max_result_age_ms:
        raise AppError(
            ErrorCode.FRAME_TOO_OLD,
            "The frame expired while waiting for local inference.",
            status_code=409,
            retryable=True,
            details={"max_result_age_ms": settings.max_result_age_ms},
        )

    decode_started = perf_counter()
    decoded = decode_jpeg(
        frame_bytes,
        rotation_degrees=rotation_degrees,
        max_image_width=settings.max_image_width,
        max_image_pixels=settings.max_image_pixels,
    )
    decode_ms = (perf_counter() - decode_started) * 1000
    del frame_bytes

    detection_started = perf_counter()
    try:
        candidates = await run_in_threadpool(detector.detect, decoded.image)
    except Exception as exc:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local object detector could not analyze this frame.",
            status_code=503,
            retryable=True,
            details={"reason": type(exc).__name__},
        ) from exc
    detection_ms = (perf_counter() - detection_started) * 1000

    segmenter: Segmenter = request.app.state.segmenter
    segmentation: SegmentationFrame | None = None
    segmentation_ms: float | None = None
    segmentation_failed = not segmenter.ready
    if segmenter.ready:
        segmentation_started = perf_counter()
        try:
            segmentation = await run_in_threadpool(segmenter.segment, decoded.image)
        except Exception:
            segmentation_failed = True
        segmentation_ms = (perf_counter() - segmentation_started) * 1000

    tracking_started = perf_counter()
    tracking_sessions: TrackingSessionStore = request.app.state.tracking_sessions
    tracked = tracking_sessions.update(
        session_id,
        candidates,
        frame_id=frame_id,
        captured_at=captured_at,
    )
    tracking_depth_ms = (perf_counter() - tracking_started) * 1000

    spatial_started = perf_counter()
    corridor = analyze_corridors(tracked, settings, segmentation)
    surfaces = (
        extract_surface_regions(segmentation, frame_id=frame_id)
        if segmentation is not None
        else []
    )
    spatial_ms = (perf_counter() - spatial_started) * 1000

    valid_until = captured_at + timedelta(milliseconds=settings.max_result_age_ms)
    risk_started = perf_counter()
    session_settings = session.request.settings
    risk_sensitivity = (
        session_settings.risk_sensitivity
        if session_settings is not None
        and session_settings.risk_sensitivity is not None
        else 0.5
    )
    assessments = score_tracks(
        corridor.tracks,
        settings,
        risk_sensitivity=risk_sensitivity,
    )
    proposed = select_action(assessments, corridor, settings)
    risk_sessions: RiskSessionStore = request.app.state.risk_sessions
    decision = risk_sessions.apply(session_id, proposed, now=captured_at)
    haptics_enabled = not (
        session_settings is not None
        and session_settings.haptics_enabled is False
    )
    guidance = build_guidance(decision, haptics_enabled=haptics_enabled)
    overlay = build_overlay(
        decision,
        corridor,
        settings,
        valid_until=valid_until,
    )
    detections = [
        _to_contract_detection(item, decision.critical_track_ids)
        for item in assessments
    ]
    risk_ms = (perf_counter() - risk_started) * 1000

    processed_at = utc_now()
    total_ms = (perf_counter() - request_started) * 1000
    degraded_modules = ["depth"]
    if segmentation_failed:
        degraded_modules[0:0] = ["segmentation", "india_hazards"]
    return FrameAnalysisResponse(
        server_time=processed_at,
        session_id=session_id,
        frame_id=frame_id,
        captured_at=captured_at,
        received_at=received_at,
        processed_at=processed_at,
        frame_age_ms=max(0.0, (processed_at - captured_at).total_seconds() * 1000),
        geometry=FrameGeometry(
            source_width=decoded.width,
            source_height=decoded.height,
            rotation_degrees=rotation_degrees,
        ),
        detections=detections,
        surfaces=surfaces,
        corridors=corridor.costs,
        overlay=overlay,
        guidance=guidance,
        timings=StageTimings(
            decode_ms=decode_ms,
            detection_ms=detection_ms,
            segmentation_ms=segmentation_ms,
            tracking_depth_ms=tracking_depth_ms,
            spatial_ms=spatial_ms,
            risk_ms=risk_ms,
            total_ms=total_ms,
        ),
        degraded_modules=degraded_modules,
    )


def _to_contract_detection(
    assessment: RiskAssessment,
    critical_track_ids: frozenset[int],
) -> DetectionResult:
    item = assessment.spatial
    candidate = item.tracked.detection
    motion_vector = (
        MotionVector(dx=item.tracked.motion_dx, dy=item.tracked.motion_dy)
        if item.tracked.motion_dx is not None and item.tracked.motion_dy is not None
        else None
    )
    return DetectionResult(
        track_id=item.tracked.track_id,
        label=candidate.label,
        confidence=candidate.confidence,
        bbox=NormalizedBoundingBox(
            x1=candidate.x1,
            y1=candidate.y1,
            x2=candidate.x2,
            y2=candidate.y2,
        ),
        anchor=NormalizedPoint(
            x=(candidate.x1 + candidate.x2) / 2,
            y=candidate.y2,
        ),
        direction=item.direction,
        proximity=item.proximity.band,
        proximity_score=item.proximity.score,
        approach_state=assessment.approach_state,
        approach_rate=item.tracked.approach_rate,
        motion_vector=motion_vector,
        path_overlap=item.path_overlap,
        risk_score=assessment.score,
        risk_level=(
            RiskLevel.CRITICAL
            if item.tracked.track_id in critical_track_ids
            else assessment.level
        ),
        display_color=_display_color(
            RiskLevel.CRITICAL
            if item.tracked.track_id in critical_track_ids
            else assessment.level
        ),
    )


def _display_color(level: RiskLevel) -> DisplayColor:
    if level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return DisplayColor.RED
    if level in {RiskLevel.WATCH, RiskLevel.WARN}:
        return DisplayColor.YELLOW
    return DisplayColor.GREY


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "captured_at must include a UTC offset.",
            status_code=422,
        )
    return value.astimezone(UTC)
