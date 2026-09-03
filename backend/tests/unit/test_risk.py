from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.guidance.actions import build_guidance
from app.perception.detector import DetectionCandidate
from app.perception.tracking import TrackedDetection
from app.risk.rules import ProposedDecision, select_action
from app.risk.scoring import score_tracks
from app.risk.state_machine import AlertStateMachine, StableDecision
from app.schemas.walk import (
    CorridorChoice,
    Direction,
    GuidanceAction,
    ProximityBand,
    RiskLevel,
    CorridorCosts,
)
from app.spatial.corridor import CorridorAnalysis, SpatialTrack
from app.spatial.proximity import RelativeProximity


def test_weighted_risk_score_uses_normalized_blueprint_features() -> None:
    settings = Settings(_env_file=None)
    detection = DetectionCandidate("chair", 0.9, 0.4, 0.4, 0.6, 0.9)
    tracked = TrackedDetection(detection, 7, 0.5, 0.5, 0.0, 0.0)
    spatial = SpatialTrack(
        tracked=tracked,
        proximity=RelativeProximity(0.8, ProximityBand.NEAR),
        direction=Direction.CENTRE,
        path_overlap=0.9,
    )

    assessment = score_tracks([spatial], settings)[0]

    assert assessment.score == pytest.approx(0.7725)
    assert assessment.level == RiskLevel.WARN
    assert assessment.approach_state == "APPROACHING"


def test_alert_persistence_cooldown_and_critical_interrupt() -> None:
    settings = Settings(
        _env_file=None,
        alert_persistence_frames=2,
        alert_cooldown_seconds=10,
    )
    machine = AlertStateMachine(settings)
    now = datetime(2026, 9, 3, tzinfo=UTC)
    move = ProposedDecision(
        action=GuidanceAction.MOVE_RIGHT,
        level=RiskLevel.HIGH,
        reason_code="CENTRE_BLOCKED_CLEARER_SIDE",
        preferred_corridor=CorridorChoice.RIGHT,
        evidence_score=0.8,
    )

    assert machine.apply(move, now=now).action == GuidanceAction.CLEAR
    announced = machine.apply(move, now=now + timedelta(milliseconds=100))
    duplicate = machine.apply(move, now=now + timedelta(milliseconds=200))
    critical = machine.apply(
        ProposedDecision(
            action=GuidanceAction.STOP,
            level=RiskLevel.CRITICAL,
            reason_code="APPROACHING_VEHICLE_CENTRE",
            preferred_corridor=CorridorChoice.NONE,
            evidence_score=1.0,
        ),
        now=now + timedelta(milliseconds=300),
    )

    assert announced.action == GuidanceAction.MOVE_RIGHT
    assert announced.speak is True
    assert duplicate.action == GuidanceAction.MOVE_RIGHT
    assert duplicate.speak is False
    assert critical.action == GuidanceAction.STOP
    assert critical.speak is True


def test_warn_exit_hysteresis_and_clear_frame_requirement() -> None:
    settings = Settings(
        _env_file=None,
        alert_persistence_frames=1,
        alert_clear_frames=3,
    )
    machine = AlertStateMachine(settings)
    now = datetime(2026, 9, 3, tzinfo=UTC)
    caution = ProposedDecision(
        action=GuidanceAction.CAUTION,
        level=RiskLevel.WARN,
        reason_code="OBSTACLE_NEARBY",
        preferred_corridor=CorridorChoice.CENTRE,
        evidence_score=0.7,
    )
    machine.apply(caution, now=now)

    hysteresis = machine.apply(
        ProposedDecision(
            action=GuidanceAction.CLEAR,
            level=RiskLevel.WATCH,
            reason_code="LOW_RISK_MONITORED",
            preferred_corridor=CorridorChoice.CENTRE,
            evidence_score=0.55,
        ),
        now=now + timedelta(seconds=1),
    )
    clear = ProposedDecision(
        action=GuidanceAction.CLEAR,
        level=RiskLevel.CLEAR,
        reason_code="PATH_CLEAR",
        preferred_corridor=CorridorChoice.CENTRE,
        evidence_score=0.1,
    )
    first = machine.apply(clear, now=now + timedelta(seconds=2))
    second = machine.apply(clear, now=now + timedelta(seconds=3))
    third = machine.apply(clear, now=now + timedelta(seconds=4))

    assert hysteresis.reason_code == "RISK_HYSTERESIS_ACTIVE"
    assert first.action == second.action == GuidanceAction.CAUTION
    assert third.action == GuidanceAction.CLEAR
    assert third.speak is False


@pytest.mark.parametrize(
    ("action", "speech", "haptic"),
    [
        (GuidanceAction.CLEAR, "", "NONE"),
        (GuidanceAction.CAUTION, "Obstacle nearby.", "CAUTION_SHORT"),
        (
            GuidanceAction.MOVE_LEFT,
            "Path blocked. Move slightly left.",
            "WARNING_DOUBLE",
        ),
        (
            GuidanceAction.MOVE_RIGHT,
            "Path blocked. Move slightly right.",
            "WARNING_DOUBLE",
        ),
        (
            GuidanceAction.STOP,
            "Stop. Obstacle directly ahead.",
            "CRITICAL_RAPID",
        ),
        (
            GuidanceAction.PAUSE_UNCLEAR,
            "Path unclear. Please pause.",
            "UNCLEAR_LONG",
        ),
    ],
)
def test_complete_action_vocabulary_has_frozen_guidance(
    action: GuidanceAction,
    speech: str,
    haptic: str,
) -> None:
    guidance = build_guidance(
        StableDecision(
            action=action,
            level=RiskLevel.CLEAR if action == GuidanceAction.CLEAR else RiskLevel.WARN,
            reason_code="TEST",
            preferred_corridor=CorridorChoice.CENTRE,
            critical_track_ids=frozenset(),
            speak=True,
        ),
        haptics_enabled=True,
    )

    assert guidance.speech == speech
    assert guidance.haptic_pattern == haptic
    assert guidance.speak is bool(speech)


def test_risk_sensitivity_changes_score_without_exceeding_contract_bounds() -> None:
    settings = Settings(_env_file=None)
    detection = DetectionCandidate("chair", 0.9, 0.4, 0.4, 0.6, 0.9)
    spatial = SpatialTrack(
        tracked=TrackedDetection(detection, 1, 0.2, 0.2, 0.0, 0.0),
        proximity=RelativeProximity(0.7, ProximityBand.NEAR),
        direction=Direction.CENTRE,
        path_overlap=0.8,
    )

    low = score_tracks([spatial], settings, risk_sensitivity=0.0)[0].score
    high = score_tracks([spatial], settings, risk_sensitivity=1.0)[0].score

    assert 0 <= low < high <= 1


def corridor_fixture(*, right_floor_extent: float, stairs_ratio: float = 0.0) -> CorridorAnalysis:
    return CorridorAnalysis(
        tracks=[],
        costs=CorridorCosts(left_cost=0.90, centre_cost=0.80, right_cost=0.20),
        preferred=CorridorChoice.RIGHT,
        walkable_choices=frozenset({CorridorChoice.RIGHT}),
        uncertain_choices=frozenset(),
        safe_polygons=[],
        blocked_polygons=[],
        uncertain_polygons=[],
        wall_ratios=CorridorCosts(left_cost=0.80, centre_cost=0.0, right_cost=0.0),
        floor_extents=CorridorCosts(
            left_cost=0.0,
            centre_cost=0.0,
            right_cost=right_floor_extent,
        ),
        stairs_ratios=CorridorCosts(
            left_cost=0.0,
            centre_cost=stairs_ratio,
            right_cost=0.0,
        ),
        wall_dead_end=False,
    )


def test_directional_guidance_requires_positive_free_space_extent() -> None:
    settings = Settings(_env_file=None)

    refused = select_action([], corridor_fixture(right_floor_extent=0.10), settings)
    allowed = select_action([], corridor_fixture(right_floor_extent=0.80), settings)

    assert refused.action == GuidanceAction.PAUSE_UNCLEAR
    assert refused.reason_code == "CENTRE_BLOCKED_DIRECTION_UNCLEAR"
    assert allowed.action == GuidanceAction.MOVE_RIGHT


def test_stairs_stop_precedes_generic_corridor_blocking() -> None:
    settings = Settings(_env_file=None)

    decision = select_action(
        [],
        corridor_fixture(right_floor_extent=0.80, stairs_ratio=0.25),
        settings,
    )

    assert decision.action == GuidanceAction.STOP
    assert decision.reason_code == "STAIRS_OR_LEVEL_CHANGE_AHEAD"
