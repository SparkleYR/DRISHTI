from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from app.config import Settings
from app.perception.detector import DetectionCandidate
from app.schemas.walk import ApproachState, ProximityBand


@dataclass(frozen=True)
class RelativeProximity:
    score: float
    band: ProximityBand


def estimate_relative_proximity(
    detection: DetectionCandidate,
    settings: Settings,
) -> RelativeProximity:
    area = (detection.x2 - detection.x1) * (detection.y2 - detection.y1)
    area_signal = min(1.0, sqrt(max(0.0, area)) / settings.proximity_area_scale)
    lower_edge_weight = 1.0 - settings.proximity_area_weight
    score = min(
        1.0,
        max(
            0.0,
            settings.proximity_area_weight * area_signal
            + lower_edge_weight * detection.y2,
        ),
    )
    if score < settings.proximity_far_threshold:
        band = ProximityBand.FAR
    elif score < settings.proximity_medium_threshold:
        band = ProximityBand.MEDIUM
    elif score < settings.proximity_near_threshold:
        band = ProximityBand.NEAR
    else:
        band = ProximityBand.IMMEDIATE
    return RelativeProximity(score=score, band=band)


def classify_approach(
    area_change: float | None,
    *,
    threshold: float,
) -> ApproachState:
    if area_change is None:
        return ApproachState.UNKNOWN
    if area_change >= threshold:
        return ApproachState.APPROACHING
    if area_change <= -threshold:
        return ApproachState.RECEDING
    return ApproachState.STATIONARY
