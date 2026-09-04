from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from app.config import Settings
from app.perception.landmark_memory import Landmark, labels_match, wrap180
from app.schemas.walk import (
    DetectionResult,
    NormalizedPoint,
    TargetGuidanceStep,
    TargetHapticPattern,
    TargetRangeHint,
    TargetTrackingState,
    TargetTrackingTelemetry,
)


@dataclass
class _GuidedSession:
    state: TargetTrackingState = TargetTrackingState.IDLE
    target_name: str | None = None
    landmark: Landmark | None = None
    guidance_step: TargetGuidanceStep = TargetGuidanceStep.NONE
    target_center: tuple[float, float] | None = None
    range_hint: TargetRangeHint = TargetRangeHint.UNKNOWN
    bearing_degrees: float | None = None
    last_range_hint: TargetRangeHint = TargetRangeHint.UNKNOWN
    last_spoken_ms: int | None = None
    arrived_since_ms: int | None = None
    lost_announcement_pending: bool = False


@dataclass(frozen=True)
class GuidanceSeed:
    state: TargetTrackingState
    bearing_degrees: float | None
    range_hint: TargetRangeHint
    target_center: tuple[float, float] | None


class TargetGuidanceSessionStore:
    """Turn-by-turn target guidance; perception and safety decisions stay external."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: dict[str, _GuidedSession] = {}
        self._lock = RLock()

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = _GuidedSession()

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def begin_seeking(self, session_id: str, target_name: str) -> None:
        with self._lock:
            self._sessions[session_id] = _GuidedSession(
                state=TargetTrackingState.SEEKING,
                target_name=target_name,
            )

    def fail_seeking(self, session_id: str, target_name: str) -> None:
        with self._lock:
            self._sessions[session_id] = _GuidedSession(
                state=TargetTrackingState.LOST,
                target_name=target_name,
                guidance_step=TargetGuidanceStep.REACQUIRE,
                lost_announcement_pending=True,
            )

    def start_guidance(
        self,
        session_id: str,
        *,
        target_name: str,
        landmark: Landmark,
        now_ms: int,
        heading_degrees: float | None,
        visible: bool,
    ) -> GuidanceSeed:
        center = (
            (landmark.last_center_x, (landmark.last_box[1] + landmark.last_box[3]) / 2.0)
            if visible
            else None
        )
        bearing = relative_bearing(
            landmark,
            heading_degrees,
            center,
            self._settings.walk_camera_hfov_degrees,
        )
        session = _GuidedSession(
            state=TargetTrackingState.GUIDING if visible else TargetTrackingState.SEEKING,
            target_name=target_name,
            landmark=replace(landmark),
            target_center=center,
            range_hint=range_hint(landmark.last_box),
            bearing_degrees=bearing,
            last_range_hint=TargetRangeHint.UNKNOWN,
        )
        with self._lock:
            self._sessions[session_id] = session
        return GuidanceSeed(session.state, bearing, session.range_hint, center)

    def step(
        self,
        session_id: str,
        *,
        now_ms: int,
        heading_degrees: float | None,
        detections: list[DetectionResult],
        is_safety_overridden: bool,
        haptics_enabled: bool,
    ) -> TargetTrackingTelemetry:
        with self._lock:
            session = self._sessions.setdefault(session_id, _GuidedSession())
            if is_safety_overridden:
                return _telemetry(session, is_safety_overridden=True)
            if session.state == TargetTrackingState.ARRIVED:
                self._sessions[session_id] = _GuidedSession()
                return _telemetry(_GuidedSession(), is_safety_overridden=False)
            if session.state == TargetTrackingState.IDLE:
                return _telemetry(session, is_safety_overridden=is_safety_overridden)
            if session.landmark is None:
                speech = ""
                speak = False
                if session.lost_announcement_pending:
                    speech = "I've lost it. Stop and scan around slowly."
                    speak = True
                    session.lost_announcement_pending = False
                return _telemetry(session, speech=speech, speak=speak)

            match = _latest_match(session.target_name or session.landmark.label, detections)
            if match is not None:
                box = (match.bbox.x1, match.bbox.y1, match.bbox.x2, match.bbox.y2)
                center = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
                world_bearing = (
                    wrap180(heading_degrees + (center[0] - 0.5) * self._settings.walk_camera_hfov_degrees)
                    if heading_degrees is not None
                    else session.landmark.world_bearing_deg
                )
                session.landmark = replace(
                    session.landmark,
                    world_bearing_deg=world_bearing,
                    last_center_x=center[0],
                    last_box_h=box[3] - box[1],
                    last_box_bottom=box[3],
                    last_box=box,
                    last_seen_ms=now_ms,
                    sightings=session.landmark.sightings + 1,
                )
                session.target_center = center
                session.range_hint = range_hint(box)
                session.state = TargetTrackingState.GUIDING
            else:
                session.target_center = None

            elapsed = now_ms - session.landmark.last_seen_ms
            if match is None and elapsed > self._settings.target_reacquire_timeout_seconds * 1000:
                changed = session.guidance_step != TargetGuidanceStep.REACQUIRE
                session.state = TargetTrackingState.LOST
                session.guidance_step = TargetGuidanceStep.REACQUIRE
                session.arrived_since_ms = None
                return _telemetry(
                    session,
                    speech="I've lost it. Stop and scan around slowly." if changed else "",
                    speak=changed,
                )

            bearing = relative_bearing(
                session.landmark,
                heading_degrees,
                session.target_center,
                self._settings.walk_camera_hfov_degrees,
            )
            session.bearing_degrees = bearing
            step, speech = self._select_step(session, bearing, now_ms)
            changed = step != session.guidance_step
            session.guidance_step = step
            speak = changed or (
                step != TargetGuidanceStep.REACQUIRE
                and session.last_spoken_ms is not None
                and now_ms - session.last_spoken_ms
                >= self._settings.target_speech_interval_seconds * 1000
            )
            if session.last_spoken_ms is None:
                speak = True
            if speak:
                session.last_spoken_ms = now_ms
            haptic = _haptic(step, bearing) if haptics_enabled else TargetHapticPattern.NONE
            telemetry = _telemetry(
                session,
                bearing=bearing,
                speech=speech if speak else "",
                speak=speak,
                haptic=haptic,
            )
            session.last_range_hint = session.range_hint
            return telemetry

    def _select_step(
        self,
        session: _GuidedSession,
        bearing: float | None,
        now_ms: int,
    ) -> tuple[TargetGuidanceStep, str]:
        if bearing is None:
            session.state = TargetTrackingState.SEEKING
            return TargetGuidanceStep.REACQUIRE, "Stop and scan around slowly."
        magnitude = abs(bearing)
        side = "right" if bearing > 0 else "left"
        if magnitude > self._settings.target_turn_threshold_degrees:
            session.arrived_since_ms = None
            return (
                TargetGuidanceStep.TURN_RIGHT if bearing > 0 else TargetGuidanceStep.TURN_LEFT,
                f"Turn {side}.",
            )
        if magnitude > self._settings.target_face_tolerance_degrees:
            session.arrived_since_ms = None
            return TargetGuidanceStep.KEEP_TURNING, f"Keep turning {side}."
        if session.range_hint == TargetRangeHint.NEAR:
            if session.arrived_since_ms is None:
                session.arrived_since_ms = now_ms
            if now_ms - session.arrived_since_ms >= self._settings.target_arrived_dwell_seconds * 1000:
                session.state = TargetTrackingState.ARRIVED
                return TargetGuidanceStep.ARRIVED, "You should be right in front of it."
        else:
            session.arrived_since_ms = None
        session.state = TargetTrackingState.GUIDING
        if (
            session.last_range_hint != TargetRangeHint.UNKNOWN
            and _range_rank(session.range_hint) > _range_rank(session.last_range_hint)
        ):
            return TargetGuidanceStep.WALKING, "Keep going."
        return TargetGuidanceStep.FACE_AND_WALK, "You're facing it. Walk forward."


def relative_bearing(
    landmark: Landmark,
    heading_degrees: float | None,
    target_center: tuple[float, float] | None,
    camera_hfov_degrees: float = 67.0,
) -> float | None:
    if heading_degrees is not None and landmark.world_bearing_deg is not None:
        return wrap180(landmark.world_bearing_deg - heading_degrees)
    if target_center is not None:
        return (target_center[0] - 0.5) * camera_hfov_degrees
    return None


def range_hint(box: tuple[float, float, float, float]) -> TargetRangeHint:
    height = box[3] - box[1]
    if height >= 0.55 or box[3] >= 0.90:
        return TargetRangeHint.NEAR
    if height <= 0.15:
        return TargetRangeHint.FAR
    return TargetRangeHint.MID


def guidance_text(target_name: str, bearing: float | None) -> str:
    if bearing is None:
        return f"{target_name.capitalize()} found. Stop and scan around slowly."
    if abs(bearing) <= 10.0:
        return f"{target_name.capitalize()} is ahead. Walk forward."
    side = "right" if bearing > 0 else "left"
    if abs(bearing) >= 135.0:
        return f"{target_name.capitalize()} is behind you on the {side}. Turn around."
    return f"{target_name.capitalize()} is to your {side}. Turn {side}."


def compatibility_clock_direction(center_x: float | None) -> str | None:
    if center_x is None:
        return None
    if center_x < 0.20:
        hour = 9
    elif center_x < 0.35:
        hour = 10
    elif center_x < 0.45:
        hour = 11
    elif center_x < 0.55:
        hour = 12
    elif center_x < 0.65:
        hour = 1
    elif center_x < 0.80:
        hour = 2
    else:
        hour = 3
    return f"{hour} o'clock"


def _latest_match(target_name: str, detections: list[DetectionResult]) -> DetectionResult | None:
    matches = [item for item in detections if labels_match(target_name, item.label)]
    return max(matches, key=lambda item: item.confidence, default=None)


def _range_rank(value: TargetRangeHint) -> int:
    return {TargetRangeHint.UNKNOWN: 0, TargetRangeHint.FAR: 1, TargetRangeHint.MID: 2, TargetRangeHint.NEAR: 3}[value]


def _haptic(step: TargetGuidanceStep, bearing: float | None) -> TargetHapticPattern:
    if step in {TargetGuidanceStep.TURN_LEFT, TargetGuidanceStep.TURN_RIGHT, TargetGuidanceStep.KEEP_TURNING}:
        return TargetHapticPattern.TARGET_RIGHT_PULSE if (bearing or 0.0) > 0 else TargetHapticPattern.TARGET_LEFT_PULSE
    if step in {TargetGuidanceStep.FACE_AND_WALK, TargetGuidanceStep.WALKING, TargetGuidanceStep.ARRIVED}:
        return TargetHapticPattern.TARGET_CENTRE_PULSE
    return TargetHapticPattern.NONE


def _telemetry(
    session: _GuidedSession,
    *,
    is_safety_overridden: bool = False,
    bearing: float | None = None,
    speech: str = "",
    speak: bool = False,
    haptic: TargetHapticPattern = TargetHapticPattern.NONE,
) -> TargetTrackingTelemetry:
    center = session.target_center
    return TargetTrackingTelemetry(
        tracking_state=session.state,
        target_name=session.target_name,
        guidance_step=session.guidance_step,
        bearing_degrees=bearing if bearing is not None else session.bearing_degrees,
        range_hint=session.range_hint,
        clock_direction=compatibility_clock_direction(center[0] if center else None),
        target_center=NormalizedPoint(x=center[0], y=center[1]) if center else None,
        confidence=None,
        is_safety_overridden=is_safety_overridden,
        speech=speech,
        speak=speak,
        haptic_pattern=haptic,
    )
