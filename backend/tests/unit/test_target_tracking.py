from __future__ import annotations

import pytest

from app.config import Settings
from app.guidance.target_guidance import TargetGuidanceSessionStore, range_hint, relative_bearing
from app.perception.landmark_memory import Landmark, LandmarkMemoryStore, labels_match, wrap180
from app.risk.priority import safety_preempts_target_guidance
from app.risk.state_machine import StableDecision
from app.schemas.walk import (
    ApproachState, CorridorChoice, DetectionResult, Direction, DisplayColor,
    GuidanceAction, NormalizedBoundingBox, NormalizedPoint, ProximityBand,
    RiskLevel, TargetGuidanceStep, TargetHapticPattern, TargetRangeHint,
    TargetTrackingState,
)


def detection(label: str, box: tuple[float, float, float, float]) -> DetectionResult:
    x1, y1, x2, y2 = box
    return DetectionResult(
        label=label, confidence=0.9,
        bbox=NormalizedBoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
        anchor=NormalizedPoint(x=(x1 + x2) / 2, y=y2),
        direction=Direction.CENTRE, proximity=ProximityBand.MEDIUM,
        approach_state=ApproachState.UNKNOWN, path_overlap=0.0, risk_score=0.0,
        risk_level=RiskLevel.CLEAR, display_color=DisplayColor.GREEN,
    )


def landmark(*, bearing: float | None = 30.0, seen_ms: int = 1_000) -> Landmark:
    return Landmark(
        label="chair", world_bearing_deg=bearing, last_center_x=0.5,
        last_box_h=0.3, last_box_bottom=0.7,
        last_box=(0.4, 0.4, 0.6, 0.7), first_seen_ms=seen_ms,
        last_seen_ms=seen_ms, sightings=1,
    )


def test_landmark_memory_resolves_recent_detector_sighting_and_expires() -> None:
    memory = LandmarkMemoryStore(
        ttl_seconds=45, max_entries=2, camera_hfov_degrees=67.0,
    )
    memory.start_session("session")
    memory.observe(
        "session", now_ms=1_000, heading_degrees=90.0,
        detections=[
            detection("chair", (0.1, 0.2, 0.3, 0.6)),
            detection("person", (0.4, 0.2, 0.6, 0.8)),
        ],
    )
    resolved = memory.resolve("session", "the chair", now_ms=2_000)
    assert resolved is not None
    assert resolved.world_bearing_deg == pytest.approx(69.9)
    assert memory.resolve("session", "person", now_ms=2_000) is None
    assert memory.resolve("session", "chair", now_ms=46_001) is None


def test_memory_matching_and_bearing_wrapping_are_deterministic() -> None:
    assert labels_match("the sofa", "couch")
    assert labels_match("blue chair", "chair")
    assert wrap180(190.0) == -170.0


def test_turn_by_turn_guidance_degrades_to_reacquire_and_safety_preempts() -> None:
    settings = Settings(_env_file=None, target_reacquire_timeout_seconds=2.0)
    store = TargetGuidanceSessionStore(settings)
    store.start_session("session")
    seed = store.start_guidance(
        "session", target_name="chair", landmark=landmark(), now_ms=1_000,
        heading_degrees=0.0, visible=False,
    )
    assert seed.bearing_degrees == pytest.approx(30.0)
    turning = store.step(
        "session", now_ms=1_100, heading_degrees=0.0, detections=[],
        is_safety_overridden=False, haptics_enabled=True,
    )
    assert turning.guidance_step == TargetGuidanceStep.TURN_RIGHT
    assert turning.speech == "Turn right."
    assert turning.haptic_pattern == TargetHapticPattern.TARGET_RIGHT_PULSE
    overridden = store.step(
        "session", now_ms=1_200, heading_degrees=0.0, detections=[],
        is_safety_overridden=True, haptics_enabled=True,
    )
    assert overridden.is_safety_overridden is True
    assert overridden.speak is False
    assert overridden.haptic_pattern == TargetHapticPattern.NONE
    lost = store.step(
        "session", now_ms=3_100, heading_degrees=180.0, detections=[],
        is_safety_overridden=False, haptics_enabled=True,
    )
    assert lost.tracking_state == TargetTrackingState.LOST
    assert lost.guidance_step == TargetGuidanceStep.REACQUIRE
    assert lost.speech == "I've lost it. Stop and scan around slowly."


def test_live_detection_reacquires_without_heading_and_reports_coarse_range() -> None:
    store = TargetGuidanceSessionStore(Settings(_env_file=None))
    store.start_session("session")
    store.start_guidance(
        "session", target_name="chair", landmark=landmark(bearing=None),
        now_ms=1_000, heading_degrees=None, visible=False,
    )
    telemetry = store.step(
        "session", now_ms=1_100, heading_degrees=None,
        detections=[detection("chair", (0.45, 0.2, 0.55, 0.5))],
        is_safety_overridden=False, haptics_enabled=True,
    )
    assert telemetry.tracking_state == TargetTrackingState.GUIDING
    assert telemetry.guidance_step == TargetGuidanceStep.FACE_AND_WALK
    assert telemetry.bearing_degrees == pytest.approx(0.0)
    assert telemetry.range_hint == TargetRangeHint.MID
    assert range_hint((0.2, 0.2, 0.8, 0.95)) == TargetRangeHint.NEAR
    assert relative_bearing(landmark(bearing=None), None, (0.25, 0.5)) == pytest.approx(-16.75)


@pytest.mark.parametrize("action", list(GuidanceAction))
def test_every_actionable_risk_decision_preempts_target_guidance(action: GuidanceAction) -> None:
    decision = StableDecision(
        action=action,
        level=RiskLevel.CLEAR if action == GuidanceAction.CLEAR else RiskLevel.WARN,
        reason_code="test", preferred_corridor=CorridorChoice.CENTRE,
        critical_track_ids=frozenset(), speak=False,
    )
    assert safety_preempts_target_guidance(decision) is (action != GuidanceAction.CLEAR)
