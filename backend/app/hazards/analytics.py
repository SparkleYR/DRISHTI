from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models import AccessibilityRoute, AccessibilitySegment, Hazard
from app.schemas.hazards import (
    AccessibilityBand,
    AccessibilityFactor,
    HazardSeverity,
    HazardStatus,
    RouteAccessibilityScore,
    RouteSegmentRecord,
    SegmentAccessibilityScore,
    VersionedMapCoordinate,
)


SEVERITY_POINTS = {
    HazardSeverity.LOW: 8.0,
    HazardSeverity.MEDIUM: 16.0,
    HazardSeverity.HIGH: 28.0,
    HazardSeverity.CRITICAL: 40.0,
}
STATUS_FACTORS = {
    HazardStatus.NEW: 0.60,
    HazardStatus.VERIFIED: 1.00,
    HazardStatus.ASSIGNED: 0.90,
    HazardStatus.IN_PROGRESS: 0.75,
}


@dataclass(frozen=True)
class ScoringPolicy:
    temporary_ttl_seconds: int
    person_ttl_seconds: int


def accessibility_band(score: float) -> AccessibilityBand:
    if score >= 85:
        return AccessibilityBand.HIGH_ACCESS
    if score >= 65:
        return AccessibilityBand.MODERATE_ACCESS
    if score >= 40:
        return AccessibilityBand.LOW_ACCESS
    return AccessibilityBand.SEVERELY_OBSTRUCTED


def canonical_category(category: str) -> str:
    value = " ".join(category.lower().strip().replace("_", " ").split())
    aliases = {
        "backpack": "bag",
        "bag obstruction": "bag",
        "chair obstruction": "chair",
        "desk obstruction": "desk",
        "dining table": "desk",
        "table": "desk",
        "table obstruction": "desk",
        "person obstruction": "person",
        "wall or dead end": "wall",
        "wall/dead end": "wall",
    }
    return aliases.get(value, value)


def temporary_ttl_seconds(hazard: Hazard, policy: ScoringPolicy) -> int:
    if canonical_category(hazard.category) == "person":
        return policy.person_ttl_seconds
    return policy.temporary_ttl_seconds


def score_route(
    route: AccessibilityRoute,
    segments: list[AccessibilitySegment],
    hazards: list[Hazard],
    *,
    now: datetime,
    policy: ScoringPolicy,
) -> RouteAccessibilityScore:
    now_utc = _as_utc(now)
    segment_scores: list[SegmentAccessibilityScore] = []
    affecting_hazard_ids: set[str] = set()

    for segment in sorted(segments, key=lambda item: (item.sequence, item.id)):
        factors: list[AccessibilityFactor] = []
        for hazard in hazards:
            if hazard.map_x is None or hazard.map_y is None:
                continue
            distance = point_to_segment_distance(
                hazard.map_x,
                hazard.map_y,
                segment.start_x,
                segment.start_y,
                segment.end_x,
                segment.end_y,
            )
            if distance > segment.corridor_radius:
                continue
            factor = _score_factor(hazard, segment, distance, now_utc, policy)
            if factor.penalty_points <= 0:
                continue
            factors.append(factor)
            affecting_hazard_ids.add(hazard.id)
        factors.sort(key=lambda item: (-item.penalty_points, item.hazard_id))
        segment_score = round(max(0.0, 100.0 - sum(item.penalty_points for item in factors)), 1)
        segment_scores.append(
            SegmentAccessibilityScore(
                segment=_segment_record(route, segment),
                score=segment_score,
                band=accessibility_band(segment_score),
                factors=factors,
            )
        )

    if segment_scores:
        weights = [
            max(0.001, math.hypot(item.end_x - item.start_x, item.end_y - item.start_y))
            for item in sorted(segments, key=lambda item: (item.sequence, item.id))
        ]
        route_score = round(
            sum(item.score * weight for item, weight in zip(segment_scores, weights, strict=True))
            / sum(weights),
            1,
        )
    else:
        route_score = 100.0

    recurring = sum(
        1 for item in hazards if item.id in affecting_hazard_ids and item.confirmation_count > 1
    )
    return RouteAccessibilityScore(
        route_id=route.id,
        route_key=route.route_key,
        route_name=route.name,
        description=route.description,
        map_id=route.map_id,
        map_version=route.map_version,
        specification_version=route.specification_version,
        score=route_score,
        band=accessibility_band(route_score),
        active_hazard_count=len(affecting_hazard_ids),
        recurring_hazard_count=recurring,
        segments=segment_scores,
    )


def point_to_segment_distance(
    point_x: float,
    point_y: float,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> float:
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared == 0:
        return math.hypot(point_x - start_x, point_y - start_y)
    projection = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / length_squared
    projection = max(0.0, min(1.0, projection))
    nearest_x = start_x + projection * delta_x
    nearest_y = start_y + projection * delta_y
    return math.hypot(point_x - nearest_x, point_y - nearest_y)


def _score_factor(
    hazard: Hazard,
    segment: AccessibilitySegment,
    distance: float,
    now: datetime,
    policy: ScoringPolicy,
) -> AccessibilityFactor:
    severity = HazardSeverity(hazard.severity)
    status = HazardStatus(hazard.status)
    age_seconds = max(0.0, (now - _as_utc(hazard.last_seen_at)).total_seconds())
    severity_points = SEVERITY_POINTS[severity]
    status_factor = STATUS_FACTORS[status]
    recurrence_factor = min(1.5, 1.0 + max(0, hazard.confirmation_count - 1) * 0.1)
    confidence_factor = 0.5 + 0.5 * hazard.confidence
    if hazard.temporary:
        ttl = temporary_ttl_seconds(hazard, policy)
        freshness_factor = max(0.0, min(1.0, 1.0 - age_seconds / ttl))
    else:
        freshness_factor = 1.0
    spatial_factor = max(0.0, min(1.0, 1.0 - distance / segment.corridor_radius))
    penalty = round(
        min(
            60.0,
            severity_points
            * status_factor
            * recurrence_factor
            * confidence_factor
            * freshness_factor
            * spatial_factor,
        ),
        1,
    )
    explanation = (
        f"{hazard.category}: {severity.value.lower()} severity, "
        f"{hazard.confirmation_count} observation(s), {round(hazard.confidence * 100)}% confidence, "
        f"{status.value.lower()} status, {round(spatial_factor * 100)}% corridor influence."
    )
    return AccessibilityFactor(
        hazard_id=hazard.id,
        category=hazard.category,
        severity=severity,
        status=status,
        confirmation_count=hazard.confirmation_count,
        confidence=hazard.confidence,
        temporary=hazard.temporary,
        age_seconds=round(age_seconds, 1),
        distance_to_segment=round(distance, 4),
        severity_points=severity_points,
        status_factor=status_factor,
        recurrence_factor=recurrence_factor,
        confidence_factor=round(confidence_factor, 4),
        freshness_factor=round(freshness_factor, 4),
        spatial_factor=round(spatial_factor, 4),
        penalty_points=penalty,
        explanation=explanation,
    )


def _segment_record(
    route: AccessibilityRoute, segment: AccessibilitySegment
) -> RouteSegmentRecord:
    coordinate = {
        "map_id": route.map_id,
        "map_version": route.map_version,
    }
    return RouteSegmentRecord(
        id=segment.id,
        segment_key=segment.segment_key,
        name=segment.name,
        sequence=segment.sequence,
        start=VersionedMapCoordinate(**coordinate, x=segment.start_x, y=segment.start_y),
        end=VersionedMapCoordinate(**coordinate, x=segment.end_x, y=segment.end_y),
        corridor_radius=segment.corridor_radius,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
