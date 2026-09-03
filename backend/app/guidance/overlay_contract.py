from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.risk.state_machine import StableDecision
from app.schemas.walk import (
    CorridorChoice,
    DirectionArrow,
    GuidanceAction,
    NormalizedPoint,
    OverlayContract,
)
from app.spatial.corridor import CorridorAnalysis, corridor_polygons


def build_overlay(
    decision: StableDecision,
    corridor: CorridorAnalysis,
    settings: Settings,
    *,
    valid_until: datetime,
) -> OverlayContract:
    polygons = corridor_polygons(settings)
    blocked_choices = {
        choice
        for choice, cost in _costs_by_choice(corridor).items()
        if cost
        >= (
            settings.risk_centre_block_threshold
            if choice == CorridorChoice.CENTRE
            else settings.risk_side_block_threshold
        )
    }
    uncertain_choices = set(corridor.uncertain_choices)
    safe_choices: set[CorridorChoice] = set()

    if decision.action == GuidanceAction.CLEAR:
        if CorridorChoice.CENTRE in corridor.walkable_choices:
            safe_choices.add(CorridorChoice.CENTRE)
    elif decision.action == GuidanceAction.CAUTION:
        if CorridorChoice.CENTRE in corridor.walkable_choices:
            safe_choices.add(CorridorChoice.CENTRE)
    elif decision.action in {GuidanceAction.MOVE_LEFT, GuidanceAction.MOVE_RIGHT}:
        safe_choices.add(decision.preferred_corridor)
        blocked_choices.add(CorridorChoice.CENTRE)
        uncertain_choices.discard(decision.preferred_corridor)
    elif decision.action == GuidanceAction.STOP:
        safe_choices.clear()
        blocked_choices.add(CorridorChoice.CENTRE)
    elif decision.action == GuidanceAction.PAUSE_UNCLEAR:
        safe_choices.clear()
        if not uncertain_choices:
            uncertain_choices.update(polygons)

    blocked_choices.difference_update(safe_choices)
    uncertain_choices.difference_update(safe_choices)
    return OverlayContract(
        preferred_corridor=(
            decision.preferred_corridor if safe_choices else CorridorChoice.NONE
        ),
        safe_polygons=[
            _contract_polygon(polygons[item]) for item in _ordered(safe_choices)
        ],
        blocked_polygons=[
            _contract_polygon(polygons[item]) for item in _ordered(blocked_choices)
        ],
        uncertain_polygons=[
            _contract_polygon(polygons[item]) for item in _ordered(uncertain_choices)
        ],
        direction_arrow=_direction_arrow(decision.action),
        valid_until=valid_until,
    )


def _costs_by_choice(corridor: CorridorAnalysis) -> dict[CorridorChoice, float]:
    return {
        CorridorChoice.LEFT: corridor.costs.left_cost,
        CorridorChoice.CENTRE: corridor.costs.centre_cost,
        CorridorChoice.RIGHT: corridor.costs.right_cost,
    }


def _contract_polygon(
    polygon: list[tuple[float, float]],
) -> list[NormalizedPoint]:
    return [NormalizedPoint(x=x, y=y) for x, y in polygon]


def _ordered(choices: set[CorridorChoice]) -> list[CorridorChoice]:
    return [
        choice
        for choice in (
            CorridorChoice.LEFT,
            CorridorChoice.CENTRE,
            CorridorChoice.RIGHT,
        )
        if choice in choices
    ]


def _direction_arrow(action: GuidanceAction) -> DirectionArrow:
    return {
        GuidanceAction.MOVE_LEFT: DirectionArrow.LEFT,
        GuidanceAction.MOVE_RIGHT: DirectionArrow.RIGHT,
        GuidanceAction.STOP: DirectionArrow.STOP,
    }.get(action, DirectionArrow.NONE)
