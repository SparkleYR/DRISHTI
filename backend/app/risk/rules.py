from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.risk.scoring import RiskAssessment
from app.schemas.walk import (
    ApproachState,
    CorridorChoice,
    Direction,
    GuidanceAction,
    ProximityBand,
    RiskLevel,
)
from app.spatial.corridor import CorridorAnalysis


VEHICLE_LABELS = frozenset({"bicycle", "motorcycle", "car", "bus"})


@dataclass(frozen=True)
class ProposedDecision:
    action: GuidanceAction
    level: RiskLevel
    reason_code: str
    preferred_corridor: CorridorChoice
    evidence_score: float = 0.0
    critical_track_ids: frozenset[int] = frozenset()


def select_action(
    assessments: list[RiskAssessment],
    corridor: CorridorAnalysis,
    settings: Settings,
) -> ProposedDecision:
    highest_score = max((assessment.score for assessment in assessments), default=0.0)
    critical_vehicles = frozenset(
        assessment.spatial.tracked.track_id
        for assessment in assessments
        if _is_critical_approaching_vehicle(assessment, settings)
    )
    if critical_vehicles:
        return ProposedDecision(
            action=GuidanceAction.STOP,
            level=RiskLevel.CRITICAL,
            reason_code="APPROACHING_VEHICLE_CENTRE",
            preferred_corridor=CorridorChoice.NONE,
            evidence_score=highest_score,
            critical_track_ids=critical_vehicles,
        )

    if corridor.wall_dead_end:
        return ProposedDecision(
            action=GuidanceAction.STOP,
            level=RiskLevel.HIGH,
            reason_code="WALL_OR_DEAD_END_AHEAD",
            preferred_corridor=CorridorChoice.NONE,
            evidence_score=corridor.wall_ratios.centre_cost,
        )

    centre_assessments = [
        assessment
        for assessment in assessments
        if assessment.spatial.direction == Direction.CENTRE
        and assessment.spatial.path_overlap >= 0.25
    ]
    centre_blocked = (
        corridor.costs.centre_cost >= settings.risk_centre_block_threshold
        or any(
            assessment.level in {RiskLevel.WARN, RiskLevel.HIGH}
            and assessment.spatial.proximity.band
            in {ProximityBand.NEAR, ProximityBand.IMMEDIATE}
            for assessment in centre_assessments
        )
    )
    left_blocked = corridor.costs.left_cost >= settings.risk_side_block_threshold
    right_blocked = corridor.costs.right_cost >= settings.risk_side_block_threshold

    immediate_centre = any(
        assessment.spatial.proximity.band == ProximityBand.IMMEDIATE
        for assessment in centre_assessments
    )
    if centre_blocked and left_blocked and right_blocked:
        return ProposedDecision(
            action=GuidanceAction.STOP,
            level=RiskLevel.CRITICAL if immediate_centre else RiskLevel.HIGH,
            reason_code="ALL_CORRIDORS_BLOCKED",
            preferred_corridor=CorridorChoice.NONE,
            evidence_score=highest_score,
            critical_track_ids=frozenset(
                assessment.spatial.tracked.track_id
                for assessment in centre_assessments
                if immediate_centre
            ),
        )

    if centre_blocked:
        preferred = _clearer_side(corridor, settings.decision_margin)
        if (
            preferred in {CorridorChoice.LEFT, CorridorChoice.RIGHT}
            and preferred in corridor.walkable_choices
            and preferred not in corridor.uncertain_choices
        ):
            return ProposedDecision(
                action=(
                    GuidanceAction.MOVE_LEFT
                    if preferred == CorridorChoice.LEFT
                    else GuidanceAction.MOVE_RIGHT
                ),
                level=RiskLevel.HIGH,
                reason_code="CENTRE_BLOCKED_CLEARER_SIDE",
                preferred_corridor=preferred,
                evidence_score=highest_score,
            )
        return ProposedDecision(
            action=GuidanceAction.PAUSE_UNCLEAR,
            level=RiskLevel.WARN,
            reason_code="CENTRE_BLOCKED_DIRECTION_UNCLEAR",
            preferred_corridor=CorridorChoice.NONE,
            evidence_score=highest_score,
        )

    if CorridorChoice.CENTRE in corridor.uncertain_choices:
        return ProposedDecision(
            action=GuidanceAction.PAUSE_UNCLEAR,
            level=RiskLevel.WARN,
            reason_code="CENTRE_SURFACE_UNCERTAIN",
            preferred_corridor=CorridorChoice.NONE,
            evidence_score=highest_score,
        )

    highest = max(assessments, key=lambda item: item.score, default=None)
    if highest is not None and highest.level in {RiskLevel.WARN, RiskLevel.HIGH}:
        return ProposedDecision(
            action=GuidanceAction.CAUTION,
            level=RiskLevel.WARN,
            reason_code="OBSTACLE_NEARBY",
            preferred_corridor=CorridorChoice.CENTRE,
            evidence_score=highest_score,
        )
    return ProposedDecision(
        action=GuidanceAction.CLEAR,
        level=highest.level if highest is not None else RiskLevel.CLEAR,
        reason_code=("LOW_RISK_MONITORED" if highest is not None else "PATH_CLEAR"),
        preferred_corridor=CorridorChoice.CENTRE,
        evidence_score=highest_score,
    )


def _clearer_side(
    corridor: CorridorAnalysis,
    decision_margin: float,
) -> CorridorChoice:
    left = corridor.costs.left_cost
    right = corridor.costs.right_cost
    if left + decision_margin < right:
        return CorridorChoice.LEFT
    if right + decision_margin < left:
        return CorridorChoice.RIGHT
    return CorridorChoice.NONE


def _is_critical_approaching_vehicle(
    assessment: RiskAssessment,
    settings: Settings,
) -> bool:
    spatial = assessment.spatial
    return (
        spatial.tracked.detection.label in VEHICLE_LABELS
        and spatial.direction == Direction.CENTRE
        and assessment.approach_state == ApproachState.APPROACHING
        and (spatial.tracked.approach_rate or 0.0)
        >= settings.risk_critical_approach
        and spatial.path_overlap >= settings.risk_critical_path_overlap
        and spatial.proximity.score >= settings.risk_critical_proximity
    )
