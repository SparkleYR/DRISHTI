from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.config import Settings
from app.perception.tracking import TrackedDetection
from app.perception.segmenter import SegmentationFrame
from app.schemas.walk import (
    CorridorChoice,
    CorridorCosts,
    Direction,
    NormalizedPoint,
    SurfaceKind,
)
from app.spatial.proximity import RelativeProximity, estimate_relative_proximity
from app.spatial.surfaces import (
    HAZARD_SURFACE_TOKENS,
    semantic_class_ids,
    semantic_kind_map,
)


Polygon = list[tuple[float, float]]
MIN_WALKABLE_RATIO = 0.25
MIN_BLOCKING_SURFACE_RATIO = 0.20


@dataclass(frozen=True)
class SpatialTrack:
    tracked: TrackedDetection
    proximity: RelativeProximity
    direction: Direction
    path_overlap: float


@dataclass(frozen=True)
class CorridorAnalysis:
    tracks: list[SpatialTrack]
    costs: CorridorCosts
    preferred: CorridorChoice
    walkable_choices: frozenset[CorridorChoice]
    uncertain_choices: frozenset[CorridorChoice]
    safe_polygons: list[list[NormalizedPoint]]
    blocked_polygons: list[list[NormalizedPoint]]
    uncertain_polygons: list[list[NormalizedPoint]]
    wall_ratios: CorridorCosts
    floor_extents: CorridorCosts
    stairs_ratios: CorridorCosts
    wall_dead_end: bool


def analyze_corridors(
    tracks: list[TrackedDetection],
    settings: Settings,
    segmentation: SegmentationFrame | None = None,
) -> CorridorAnalysis:
    polygons = corridor_polygons(settings)
    spatial_tracks: list[SpatialTrack] = []
    costs = {choice: 0.0 for choice in polygons}

    for tracked in tracks:
        detection = tracked.detection
        proximity = estimate_relative_proximity(detection, settings)
        spatial = SpatialTrack(
            tracked=tracked,
            proximity=proximity,
            direction=direction_for_anchor(
                (detection.x1 + detection.x2) / 2,
                detection.y2,
                settings,
            ),
            path_overlap=bbox_path_overlap(detection, settings),
        )
        spatial_tracks.append(spatial)

        bbox_area = max(
            1e-6,
            (detection.x2 - detection.x1) * (detection.y2 - detection.y1),
        )
        for choice, polygon in polygons.items():
            overlap = _intersection_area(_bbox_polygon(detection), polygon) / bbox_area
            contribution = min(
                1.0,
                overlap
                * (0.35 + 0.65 * proximity.score)
                * detection.confidence,
            )
            costs[choice] = 1.0 - (1.0 - costs[choice]) * (1.0 - contribution)

    surface_ratios: dict[CorridorChoice, dict[SurfaceKind, float]] = {}
    wall_ratios = {choice: 0.0 for choice in polygons}
    floor_extents = {choice: 0.0 for choice in polygons}
    stairs_ratios = {choice: 0.0 for choice in polygons}
    if segmentation is not None:
        kind_map = semantic_kind_map(
            segmentation,
            label_set=settings.segmentation_label_set,
        )
        for choice, polygon in polygons.items():
            ratios = _surface_ratios(kind_map, polygon)
            surface_ratios[choice] = ratios
            surface_cost = min(
                1.0,
                ratios[SurfaceKind.NON_WALKABLE]
                + settings.surface_cost_road_weight * ratios[SurfaceKind.ROAD]
                + settings.surface_cost_unknown_weight * ratios[SurfaceKind.UNKNOWN],
            )
            costs[choice] = 1.0 - (1.0 - costs[choice]) * (1.0 - surface_cost)
            wall_ratios[choice] = _semantic_token_ratio(
                segmentation,
                polygon,
                tokens=frozenset({"wall"}),
                minimum_confidence=settings.wall_min_pixel_confidence,
            )
            stairs_ratios[choice] = _semantic_token_ratio(
                segmentation,
                polygon,
                tokens=HAZARD_SURFACE_TOKENS,
                minimum_confidence=settings.wall_min_pixel_confidence,
            )
            floor_extents[choice] = _floor_extent(kind_map, polygon)

    corridor_costs = CorridorCosts(
        left_cost=costs[CorridorChoice.LEFT],
        centre_cost=costs[CorridorChoice.CENTRE],
        right_cost=costs[CorridorChoice.RIGHT],
    )
    wall_corridor_ratios = CorridorCosts(
        left_cost=wall_ratios[CorridorChoice.LEFT],
        centre_cost=wall_ratios[CorridorChoice.CENTRE],
        right_cost=wall_ratios[CorridorChoice.RIGHT],
    )
    floor_corridor_extents = CorridorCosts(
        left_cost=floor_extents[CorridorChoice.LEFT],
        centre_cost=floor_extents[CorridorChoice.CENTRE],
        right_cost=floor_extents[CorridorChoice.RIGHT],
    )
    stairs_corridor_ratios = CorridorCosts(
        left_cost=stairs_ratios[CorridorChoice.LEFT],
        centre_cost=stairs_ratios[CorridorChoice.CENTRE],
        right_cost=stairs_ratios[CorridorChoice.RIGHT],
    )
    wall_dead_end = (
        floor_corridor_extents.centre_cost <= settings.freespace_dead_end_max
        and floor_corridor_extents.left_cost < settings.freespace_side_open_min
        and floor_corridor_extents.right_cost < settings.freespace_side_open_min
        and wall_corridor_ratios.centre_cost >= settings.wall_centre_ratio_threshold
    )
    walkable_choices = frozenset(
        choice
        for choice, ratios in surface_ratios.items()
        if ratios[SurfaceKind.WALKABLE] >= MIN_WALKABLE_RATIO
    )
    uncertain_choices = frozenset(
        choice
        for choice in polygons
        if segmentation is None
        or (
            surface_ratios[choice][SurfaceKind.WALKABLE] < MIN_WALKABLE_RATIO
            and surface_ratios[choice][SurfaceKind.NON_WALKABLE]
            < MIN_BLOCKING_SURFACE_RATIO
        )
    )
    preferred = _preferred_corridor(costs, settings.corridor_clear_margin)
    if (
        preferred == CorridorChoice.NONE
        and CorridorChoice.CENTRE in walkable_choices
        and costs[CorridorChoice.CENTRE] < settings.risk_centre_block_threshold
    ):
        preferred = CorridorChoice.CENTRE
    preferred_is_walkable = preferred in walkable_choices
    safe = (
        [_normalized_polygon(polygons[preferred])]
        if preferred in polygons
        and preferred_is_walkable
        and costs[preferred]
        < (
            settings.risk_centre_block_threshold
            if preferred == CorridorChoice.CENTRE
            else settings.risk_side_block_threshold
        )
        else []
    )
    blocked = [
        _normalized_polygon(polygon)
        for choice, polygon in polygons.items()
        if costs[choice]
        >= (
            settings.risk_centre_block_threshold
            if choice == CorridorChoice.CENTRE
            else settings.risk_side_block_threshold
        )
    ]
    uncertain = [
        _normalized_polygon(polygon)
        for choice, polygon in polygons.items()
        if choice in uncertain_choices
    ]
    return CorridorAnalysis(
        tracks=spatial_tracks,
        costs=corridor_costs,
        preferred=preferred,
        walkable_choices=walkable_choices,
        uncertain_choices=uncertain_choices,
        safe_polygons=safe,
        blocked_polygons=blocked,
        uncertain_polygons=uncertain,
        wall_ratios=wall_corridor_ratios,
        floor_extents=floor_corridor_extents,
        stairs_ratios=stairs_corridor_ratios,
        wall_dead_end=wall_dead_end,
    )


def corridor_polygons(settings: Settings) -> dict[CorridorChoice, Polygon]:
    top_left = 0.5 - settings.corridor_top_half_width
    top_right = 0.5 + settings.corridor_top_half_width
    bottom_left = 0.5 - settings.corridor_bottom_half_width
    bottom_right = 0.5 + settings.corridor_bottom_half_width

    def point(fraction: float, *, top: bool) -> tuple[float, float]:
        left, right, y = (
            (top_left, top_right, settings.corridor_horizon_y)
            if top
            else (bottom_left, bottom_right, 1.0)
        )
        return (left + (right - left) * fraction, y)

    return {
        CorridorChoice.LEFT: [point(0, top=True), point(1 / 3, top=True), point(1 / 3, top=False), point(0, top=False)],
        CorridorChoice.CENTRE: [point(1 / 3, top=True), point(2 / 3, top=True), point(2 / 3, top=False), point(1 / 3, top=False)],
        CorridorChoice.RIGHT: [point(2 / 3, top=True), point(1, top=True), point(1, top=False), point(2 / 3, top=False)],
    }


def direction_for_anchor(x: float, y: float, settings: Settings) -> Direction:
    if y < settings.corridor_horizon_y or y > 1.0:
        return Direction.UNKNOWN
    progress = (y - settings.corridor_horizon_y) / (1.0 - settings.corridor_horizon_y)
    half_width = settings.corridor_top_half_width + progress * (
        settings.corridor_bottom_half_width - settings.corridor_top_half_width
    )
    left = 0.5 - half_width
    right = 0.5 + half_width
    if x < left or x > right:
        return Direction.UNKNOWN
    fraction = (x - left) / (right - left)
    if fraction < 1 / 3:
        return Direction.LEFT
    if fraction < 2 / 3:
        return Direction.CENTRE
    return Direction.RIGHT


def bbox_path_overlap(detection, settings: Settings) -> float:
    bbox = _bbox_polygon(detection)
    bbox_area = max(
        1e-6,
        (detection.x2 - detection.x1) * (detection.y2 - detection.y1),
    )
    full_corridor = [
        (0.5 - settings.corridor_top_half_width, settings.corridor_horizon_y),
        (0.5 + settings.corridor_top_half_width, settings.corridor_horizon_y),
        (0.5 + settings.corridor_bottom_half_width, 1.0),
        (0.5 - settings.corridor_bottom_half_width, 1.0),
    ]
    return min(1.0, max(0.0, _intersection_area(bbox, full_corridor) / bbox_area))


def _preferred_corridor(
    costs: dict[CorridorChoice, float],
    margin: float,
) -> CorridorChoice:
    ranked = sorted(costs.items(), key=lambda item: item[1])
    if ranked[1][1] - ranked[0][1] < margin:
        return CorridorChoice.NONE
    return ranked[0][0]


def _bbox_polygon(detection) -> Polygon:
    return [
        (detection.x1, detection.y1),
        (detection.x2, detection.y1),
        (detection.x2, detection.y2),
        (detection.x1, detection.y2),
    ]


def _intersection_area(left: Polygon, right: Polygon) -> float:
    area, _ = cv2.intersectConvexConvex(
        np.asarray(left, dtype=np.float32),
        np.asarray(right, dtype=np.float32),
    )
    return float(area)


def _normalized_polygon(polygon: Polygon) -> list[NormalizedPoint]:
    return [NormalizedPoint(x=x, y=y) for x, y in polygon]


def _surface_ratios(
    kind_map: np.ndarray,
    polygon: Polygon,
) -> dict[SurfaceKind, float]:
    height, width = kind_map.shape
    pixel_polygon = np.asarray(
        [[x * (width - 1), y * (height - 1)] for x, y in polygon],
        dtype=np.int32,
    )
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, pixel_polygon, color=1)
    values = kind_map[mask == 1]
    total = max(1, values.size)
    return {
        kind: float(np.count_nonzero(values == list(SurfaceKind).index(kind))) / total
        for kind in SurfaceKind
    }


def _semantic_token_ratio(
    segmentation: SegmentationFrame,
    polygon: Polygon,
    *,
    tokens: frozenset[str],
    minimum_confidence: float,
) -> float:
    height, width = segmentation.class_map.shape
    mask = _polygon_mask((height, width), polygon)
    values = mask == 1
    total = max(1, int(np.count_nonzero(values)))
    class_ids = semantic_class_ids(segmentation, tokens)
    if not class_ids:
        return 0.0
    label_mask = np.isin(segmentation.class_map, tuple(class_ids))
    confident = segmentation.confidence_map >= minimum_confidence
    return float(np.count_nonzero(values & label_mask & confident)) / total


def _floor_extent(kind_map: np.ndarray, polygon: Polygon) -> float:
    """Median contiguous visible-floor extent from each corridor column's base."""
    height, width = kind_map.shape
    corridor_mask = _polygon_mask((height, width), polygon).astype(bool)
    walkable = kind_map == list(SurfaceKind).index(SurfaceKind.WALKABLE)
    extents: list[float] = []
    for x in range(width):
        corridor_rows = np.flatnonzero(corridor_mask[:, x])
        if corridor_rows.size == 0:
            continue
        top = int(corridor_rows[0])
        bottom = int(corridor_rows[-1])
        run_length = 0
        for y in range(bottom, top - 1, -1):
            if not corridor_mask[y, x] or not walkable[y, x]:
                break
            run_length += 1
        extents.append(run_length / max(1, bottom - top + 1))
    return float(np.median(extents)) if extents else 0.0


def _polygon_mask(shape: tuple[int, int], polygon: Polygon) -> np.ndarray:
    height, width = shape
    pixel_polygon = np.asarray(
        [[x * (width - 1), y * (height - 1)] for x, y in polygon],
        dtype=np.int32,
    )
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, pixel_polygon, color=1)
    return mask
