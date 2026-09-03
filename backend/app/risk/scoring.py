from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.schemas.walk import ApproachState, RiskLevel
from app.spatial.corridor import SpatialTrack
from app.spatial.proximity import classify_approach


@dataclass(frozen=True)
class RiskAssessment:
    spatial: SpatialTrack
    score: float
    level: RiskLevel
    class_severity: float
    approach_state: ApproachState


def score_tracks(
    tracks: list[SpatialTrack],
    settings: Settings,
    *,
    risk_sensitivity: float = 0.5,
) -> list[RiskAssessment]:
    sensitivity_factor = 0.75 + 0.5 * _clamp(risk_sensitivity)
    assessments: list[RiskAssessment] = []
    for spatial in tracks:
        tracked = spatial.tracked
        detection = tracked.detection
        class_severity = settings.risk_class_severities.get(detection.label, 0.5)
        approach = _clamp(tracked.approach_rate or 0.0)
        score = _clamp(
            (
                settings.risk_weight_path_overlap * spatial.path_overlap
                + settings.risk_weight_proximity * spatial.proximity.score
                + settings.risk_weight_approach * approach
                + settings.risk_weight_class_severity * class_severity
                + settings.risk_weight_confidence * detection.confidence
            )
            * sensitivity_factor
        )
        assessments.append(
            RiskAssessment(
                spatial=spatial,
                score=score,
                level=risk_level_for_score(score, settings),
                class_severity=class_severity,
                approach_state=classify_approach(
                    tracked.area_change,
                    threshold=settings.approach_change_threshold,
                ),
            )
        )
    return assessments


def risk_level_for_score(score: float, settings: Settings) -> RiskLevel:
    if score >= settings.risk_high_enter:
        return RiskLevel.HIGH
    if score >= settings.risk_warn_enter:
        return RiskLevel.WARN
    if score >= settings.risk_watch_enter:
        return RiskLevel.WATCH
    return RiskLevel.CLEAR


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
