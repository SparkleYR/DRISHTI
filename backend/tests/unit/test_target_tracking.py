from __future__ import annotations

import numpy as np
import pytest

from app.perception.target_tracking import (
    TargetTrackingSessionStore,
    clock_direction,
)
from app.risk.priority import safety_preempts_target_guidance
from app.risk.state_machine import StableDecision
from app.schemas.walk import (
    CorridorChoice,
    GuidanceAction,
    RiskLevel,
    TargetHapticPattern,
    TargetTrackingState,
)


class FakeTracker:
    def __init__(self) -> None:
        self.initial_box: tuple[int, int, int, int] | None = None
        self.next_result = (True, (42.0, 20.0, 30.0, 40.0))

    def init(self, _image: np.ndarray, box: tuple[int, int, int, int]) -> bool:
        self.initial_box = box
        return True

    def update(self, _image: np.ndarray):
        return self.next_result


def test_target_handoff_tracks_direction_then_announces_loss() -> None:
    tracker = FakeTracker()
    store = TargetTrackingSessionStore(
        confidence_threshold=0.20,
        tracker_factory=lambda: tracker,
    )
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:60, 20:50] = (0, 180, 255)
    image[20:60, 42:72] = (0, 180, 255)
    store.start_session("session")
    store.begin_locating("session", "registration desk")
    locating = store.telemetry(
        "session", is_safety_overridden=False, haptics_enabled=True
    )
    assert locating.tracking_state == TargetTrackingState.LOCATING

    assert store.lock_target(
        "session", "registration desk", image, (0.20, 0.20, 0.50, 0.60)
    )
    assert tracker.initial_box == (20, 20, 30, 40)
    store.update("session", image)
    locked = store.telemetry(
        "session", is_safety_overridden=False, haptics_enabled=True
    )
    assert locked.tracking_state == TargetTrackingState.LOCKED_TRACKING
    assert locked.target_center is not None
    assert locked.target_center.x == pytest.approx(0.57)
    assert locked.clock_direction == "1 o'clock"
    assert locked.speak is True
    assert locked.haptic_pattern == TargetHapticPattern.TARGET_RIGHT_PULSE

    tracker.next_result = (False, (0.0, 0.0, 0.0, 0.0))
    store.update("session", image)
    lost = store.telemetry(
        "session", is_safety_overridden=False, haptics_enabled=True
    )
    assert lost.tracking_state == TargetTrackingState.TARGET_LOST
    assert lost.speech == "Target lost. Stop and scan again."
    assert lost.speak is True


def test_safety_override_suppresses_target_speech_without_consuming_loss() -> None:
    store = TargetTrackingSessionStore(
        confidence_threshold=0.20,
        tracker_factory=FakeTracker,
    )
    store.start_session("session")
    store.begin_locating("session", "exit sign")
    store.fail_locating("session")

    overridden = store.telemetry(
        "session", is_safety_overridden=True, haptics_enabled=True
    )
    assert overridden.is_safety_overridden is True
    assert overridden.speak is False
    assert overridden.speech == ""
    assert overridden.haptic_pattern == TargetHapticPattern.NONE

    safe = store.telemetry(
        "session", is_safety_overridden=False, haptics_enabled=True
    )
    assert safe.speak is True
    assert safe.speech == "Target lost. Stop and scan again."


@pytest.mark.parametrize(
    ("x", "expected"),
    [(0.05, "9 o'clock"), (0.35, "11 o'clock"), (0.50, "12 o'clock"), (0.95, "3 o'clock")],
)
def test_clock_direction_is_deterministic(x: float, expected: str) -> None:
    assert clock_direction(x) == expected


@pytest.mark.parametrize("action", list(GuidanceAction))
def test_every_actionable_risk_decision_preempts_target_guidance(
    action: GuidanceAction,
) -> None:
    decision = StableDecision(
        action=action,
        level=RiskLevel.CLEAR if action == GuidanceAction.CLEAR else RiskLevel.WARN,
        reason_code="test",
        preferred_corridor=CorridorChoice.CENTRE,
        critical_track_ids=frozenset(),
        speak=False,
    )
    assert safety_preempts_target_guidance(decision) is (
        action != GuidanceAction.CLEAR
    )
