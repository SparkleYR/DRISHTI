from datetime import UTC, datetime

from app.db.models import AccessibilityRoute, AccessibilitySegment, Hazard
from app.hazards.analytics import ScoringPolicy, accessibility_band, point_to_segment_distance, score_route
from app.schemas.hazards import AccessibilityBand


def test_point_to_segment_distance_and_bands_are_deterministic() -> None:
    assert point_to_segment_distance(0.5, 0.5, 0.5, 0.2, 0.5, 0.8) == 0
    assert round(point_to_segment_distance(0.7, 0.5, 0.5, 0.2, 0.5, 0.8), 3) == 0.2
    assert accessibility_band(85) == AccessibilityBand.HIGH_ACCESS
    assert accessibility_band(65) == AccessibilityBand.MODERATE_ACCESS
    assert accessibility_band(40) == AccessibilityBand.LOW_ACCESS
    assert accessibility_band(39.9) == AccessibilityBand.SEVERELY_OBSTRUCTED


def test_route_score_exposes_every_factor_and_ignores_distant_hazard() -> None:
    route = AccessibilityRoute(
        id="route-v1",
        route_key="route",
        name="Test hall",
        description="Controlled route",
        map_id="hall",
        map_version="1",
        specification_version="1.0.0",
        active=True,
    )
    segment = AccessibilitySegment(
        id="segment-1",
        route_id=route.id,
        segment_key="main",
        name="Main aisle",
        sequence=1,
        start_x=0.5,
        start_y=0.9,
        end_x=0.5,
        end_y=0.1,
        corridor_radius=0.15,
    )
    near = _hazard("near", x=0.5, confirmations=3)
    distant = _hazard("distant", x=0.9, confirmations=8)
    result = score_route(
        route,
        [segment],
        [near, distant],
        now=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        policy=ScoringPolicy(temporary_ttl_seconds=900, person_ttl_seconds=45),
    )

    assert result.score < 100
    assert result.active_hazard_count == 1
    assert result.recurring_hazard_count == 1
    factor = result.segments[0].factors[0]
    assert factor.hazard_id == "near"
    assert factor.severity_points == 28
    assert factor.status_factor == 1
    assert factor.recurrence_factor == 1.2
    assert factor.confidence_factor == 0.95
    assert factor.freshness_factor == 1
    assert factor.spatial_factor == 1
    assert factor.penalty_points > 0
    assert "3 observation(s)" in factor.explanation


def _hazard(hazard_id: str, *, x: float, confirmations: int) -> Hazard:
    seen = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    return Hazard(
        id=hazard_id,
        category="chair obstruction",
        severity="HIGH",
        status="VERIFIED",
        map_id="hall",
        map_version="1",
        map_x=x,
        map_y=0.5,
        latitude=None,
        longitude=None,
        accuracy_m=None,
        first_seen_at=seen,
        last_seen_at=seen,
        confidence=0.9,
        confirmation_count=confirmations,
        temporary=False,
        assigned_to=None,
        version=1,
        evidence_path=None,
        merged_into_id=None,
    )
