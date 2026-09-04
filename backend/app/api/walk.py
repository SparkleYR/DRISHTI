from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Annotated
import math

from fastapi import APIRouter, File, Form, Request, UploadFile, WebSocket
from starlette.websockets import WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.frame_ingress import JPEG_CONTENT_TYPE, decode_jpeg
from app.guidance.actions import build_guidance
from app.guidance.overlay_contract import build_overlay
from app.perception.detector import Detector
from app.perception.segmenter import SegmentationFrame, Segmenter
from app.perception.tracking import TrackingSessionStore
from app.perception.landmark_memory import LandmarkMemoryStore
from app.guidance.target_guidance import TargetGuidanceSessionStore
from app.risk.priority import safety_preempts_target_guidance
from app.risk.rules import select_action
from app.risk.scoring import RiskAssessment, score_tracks
from app.risk.state_machine import RiskSessionStore
from app.scheduling.latest_frame import LatestFrameScheduler
from app.scheduling.frame_memory import LatestFrameMemory
from app.scheduling.telemetry import LatestTelemetryHub
from app.schemas.common import utc_now
from app.schemas.walk import (
    ActiveWalkSession,
    ActiveWalkSessionsResponse,
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
    TargetTelemetryEvent,
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
    target_sessions: TargetGuidanceSessionStore = (
        request.app.state.target_tracking_sessions
    )
    target_sessions.start_session(session.session_id)
    landmark_memories: LandmarkMemoryStore = request.app.state.landmark_memories
    landmark_memories.start_session(session.session_id)
    return StartWalkSessionResponse(
        server_time=now,
        session_id=session.session_id,
        started_at=session.started_at,
        recommended_capture_fps=settings.recommended_capture_fps,
        max_image_width=settings.max_image_width,
        max_image_bytes=settings.max_image_bytes,
        max_result_age_ms=settings.max_result_age_ms,
    )


@router.get("/sessions/active", response_model=ActiveWalkSessionsResponse)
def list_active_walk_sessions(request: Request) -> ActiveWalkSessionsResponse:
    """Discovery for local operator surfaces (the AccessOps dashboard).

    Session ids are runtime UUIDs, so a build-time environment variable can
    never name a live session. The dashboard polls this to find one and then
    subscribes to its telemetry WebSocket. Metadata only: no frames are stored
    or served (D-018, D-022).
    """
    sessions: WalkSessionStore = request.app.state.walk_sessions
    return ActiveWalkSessionsResponse(
        server_time=utc_now(),
        sessions=[
            ActiveWalkSession(
                session_id=session.session_id,
                started_at=session.started_at,
                last_frame_id=session.last_frame_id,
                last_frame_at=session.last_frame_at,
                last_action=session.last_action,
                last_risk_level=session.last_risk_level,
            )
            for session in sessions.active_sessions()
        ],
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
    target_sessions: TargetGuidanceSessionStore = (
        request.app.state.target_tracking_sessions
    )
    target_sessions.end_session(session_id)
    landmark_memories: LandmarkMemoryStore = request.app.state.landmark_memories
    landmark_memories.end_session(session_id)
    frame_memory: LatestFrameMemory = request.app.state.latest_frame_memory
    frame_memory.end_session(session_id)
    telemetry_hub: LatestTelemetryHub = request.app.state.target_telemetry_hub
    await telemetry_hub.end_session(session_id)
    assert session.ended_at is not None
    return EndWalkSessionResponse(
        server_time=now,
        session_id=session.session_id,
        ended_at=session.ended_at,
    )


@router.websocket("/sessions/{session_id}/telemetry")
async def target_telemetry(session_id: str, websocket: WebSocket) -> None:
    try:
        websocket.app.state.walk_sessions.require_active(session_id)
    except AppError as exc:
        await websocket.close(code=4404 if exc.status_code == 404 else 4409)
        return

    hub: LatestTelemetryHub = websocket.app.state.target_telemetry_hub
    queue = await hub.subscribe(session_id)
    await websocket.accept()
    try:
        while True:
            event = await queue.get()
            if event is None:
                await websocket.close(code=1000)
                return
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(session_id, queue)


@router.post("/analyze", response_model=FrameAnalysisResponse)
async def analyze_frame(
    request: Request,
    frame: Annotated[UploadFile, File()],
    session_id: Annotated[str, Form(min_length=1)],
    frame_id: Annotated[int, Form(ge=0)],
    captured_at: Annotated[datetime, Form()],
    rotation_degrees: Annotated[RotationDegrees, Form()],
    heading_degrees: Annotated[float | None, Form()] = None,
) -> FrameAnalysisResponse:
    received_at = utc_now()
    started = perf_counter()
    settings: Settings = request.app.state.settings
    sessions: WalkSessionStore = request.app.state.walk_sessions
    session = sessions.require_active(session_id)
    if heading_degrees is not None and not math.isfinite(heading_degrees):
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "heading_degrees must be a finite number.",
            status_code=422,
        )
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
            heading_degrees=heading_degrees,
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
    heading_degrees: float | None,
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
    frame_memory: LatestFrameMemory = request.app.state.latest_frame_memory
    frame_memory.store(
        session_id,
        frame_id,
        frame_bytes,
        rotation_degrees,
        heading_degrees,
    )
    del frame_bytes

    detection_started = perf_counter()
    try:
        detected = await run_in_threadpool(detector.detect, decoded.image)
    except Exception as exc:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local object detector could not analyze this frame.",
            status_code=503,
            retryable=True,
            details={"reason": type(exc).__name__},
        ) from exc
    detection_ms = (perf_counter() - detection_started) * 1000
    candidates = detected.risk
    # Landmark memory sees the full COCO output; the risk engine, the tracker,
    # the spatial stage, and the overlay keep the audited whitelist (D-078).
    observations = detected.all if settings.landmark_full_coco else detected.risk

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
        extract_surface_regions(
            segmentation,
            frame_id=frame_id,
            label_set=settings.segmentation_label_set,
        )
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
    now_ms = int(captured_at.timestamp() * 1000)
    landmark_memories: LandmarkMemoryStore = request.app.state.landmark_memories
    landmark_memories.observe(
        session_id,
        now_ms=now_ms,
        heading_degrees=heading_degrees,
        detections=observations,
    )
    target_sessions: TargetGuidanceSessionStore = (
        request.app.state.target_tracking_sessions
    )
    target_tracking = target_sessions.step(
        session_id,
        now_ms=now_ms,
        heading_degrees=heading_degrees,
        detections=observations,
        is_safety_overridden=safety_preempts_target_guidance(decision),
        haptics_enabled=haptics_enabled,
    )
    risk_ms = (perf_counter() - risk_started) * 1000
    sessions_store: WalkSessionStore = request.app.state.walk_sessions
    sessions_store.record_frame_result(
        session_id,
        processed_at=utc_now(),
        action=decision.action,
        risk_level=decision.level,
    )

    processed_at = utc_now()
    total_ms = (perf_counter() - request_started) * 1000
    degraded_modules = ["depth"]
    if segmentation_failed:
        degraded_modules[0:0] = ["segmentation", "india_hazards"]
    response = FrameAnalysisResponse(
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
        target_tracking=target_tracking,
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
    telemetry_hub: LatestTelemetryHub = request.app.state.target_telemetry_hub
    await telemetry_hub.publish(
        TargetTelemetryEvent(
            server_time=processed_at,
            session_id=session_id,
            frame_id=frame_id,
            **target_tracking.model_dump(),
        )
    )
    return response


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
