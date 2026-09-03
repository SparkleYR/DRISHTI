import numpy as np

from app.config import Settings
from app.perception.detector import DetectionCandidate
from app.perception.segmenter import SegmentationFrame
from app.perception.tracking import TrackedDetection
from app.schemas.walk import CorridorChoice, Direction, SurfaceKind
from app.spatial.corridor import analyze_corridors, bbox_path_overlap, direction_for_anchor
from app.spatial.proximity import classify_approach, estimate_relative_proximity
from app.spatial.surfaces import extract_surface_regions, semantic_kind_map


def candidate(x1: float, y1: float, x2: float, y2: float) -> DetectionCandidate:
    return DetectionCandidate("chair", 0.9, x1, y1, x2, y2)


def tracked(item: DetectionCandidate, track_id: int = 1) -> TrackedDetection:
    return TrackedDetection(item, track_id, None, None, None, None)


def test_centre_object_has_more_path_overlap_than_edge_object() -> None:
    settings = Settings()
    centre = bbox_path_overlap(candidate(0.43, 0.55, 0.57, 0.95), settings)
    edge = bbox_path_overlap(candidate(0.0, 0.55, 0.14, 0.95), settings)
    assert centre > edge
    assert direction_for_anchor(0.5, 0.9, settings) == Direction.CENTRE
    assert direction_for_anchor(0.02, 0.9, settings) == Direction.UNKNOWN


def test_larger_lower_box_has_higher_relative_proximity() -> None:
    settings = Settings()
    far = estimate_relative_proximity(candidate(0.48, 0.3, 0.52, 0.45), settings)
    near = estimate_relative_proximity(candidate(0.3, 0.3, 0.7, 0.95), settings)
    assert near.score > far.score
    assert near.band in {"NEAR", "IMMEDIATE"}


def test_area_growth_classifies_approach_without_metric_distance() -> None:
    assert classify_approach(0.2, threshold=0.05) == "APPROACHING"
    assert classify_approach(-0.2, threshold=0.05) == "RECEDING"
    assert classify_approach(0.01, threshold=0.05) == "STATIONARY"
    assert classify_approach(None, threshold=0.05) == "UNKNOWN"


def test_obstructed_left_and_centre_make_right_corridor_clearer() -> None:
    settings = Settings(corridor_clear_margin=0.05)
    result = analyze_corridors(
        [
            tracked(candidate(0.08, 0.55, 0.38, 0.98), 1),
            tracked(candidate(0.36, 0.55, 0.64, 0.98), 2),
        ],
        settings,
    )
    assert result.costs.right_cost < result.costs.left_cost
    assert result.costs.right_cost < result.costs.centre_cost
    assert result.preferred == CorridorChoice.RIGHT


def test_segmentation_maps_sidewalk_road_and_unknown_regions() -> None:
    class_map = np.full((100, 100), 10, dtype=np.uint8)
    class_map[40:, :50] = 1
    class_map[40:, 50:] = 0
    segmentation = SegmentationFrame(
        class_map=class_map,
        confidence_map=np.full((100, 100), 0.9, dtype=np.float32),
        id_to_label={0: "road", 1: "sidewalk", 10: "sky"},
    )
    kind_map = semantic_kind_map(segmentation, label_set="ADE20K")
    regions = extract_surface_regions(
        segmentation,
        frame_id=8,
        label_set="ADE20K",
    )

    assert kind_map[80, 20] == list(SurfaceKind).index(SurfaceKind.WALKABLE)
    assert kind_map[80, 80] == list(SurfaceKind).index(SurfaceKind.ROAD)
    assert kind_map[10, 50] == list(SurfaceKind).index(SurfaceKind.UNKNOWN)
    assert {region.kind for region in regions} == {
        SurfaceKind.WALKABLE,
        SurfaceKind.ROAD,
        SurfaceKind.UNKNOWN,
    }
    assert all(region.source_frame_id == 8 for region in regions)
    assert all(3 <= len(region.polygon) <= 64 for region in regions)


def test_walkable_surface_contributes_to_preferred_corridor_polygon() -> None:
    settings = Settings(corridor_clear_margin=0.05)
    class_map = np.full((120, 120), 2, dtype=np.uint8)
    class_map[45:, 60:] = 1
    segmentation = SegmentationFrame(
        class_map=class_map,
        confidence_map=np.ones((120, 120), dtype=np.float32),
        id_to_label={1: "sidewalk", 2: "building"},
    )
    result = analyze_corridors([], settings, segmentation)
    assert result.preferred == CorridorChoice.RIGHT
    assert len(result.safe_polygons) == 1


def test_ade20k_synonym_tokens_map_indoor_floor_and_furniture() -> None:
    class_map = np.array([[1, 2, 3, 4]], dtype=np.uint8)
    segmentation = SegmentationFrame(
        class_map=class_map,
        confidence_map=np.ones_like(class_map, dtype=np.float32),
        id_to_label={
            1: "floor, flooring",
            2: "rug, carpet",
            3: "door, double door",
            4: "road, route",
        },
    )

    kinds = semantic_kind_map(segmentation, label_set="ADE20K")

    assert kinds.tolist() == [[
        list(SurfaceKind).index(SurfaceKind.WALKABLE),
        list(SurfaceKind).index(SurfaceKind.WALKABLE),
        list(SurfaceKind).index(SurfaceKind.NON_WALKABLE),
        list(SurfaceKind).index(SurfaceKind.ROAD),
    ]]


def test_clear_indoor_floor_has_high_extent_and_safe_centre() -> None:
    settings = Settings(_env_file=None)
    segmentation = SegmentationFrame(
        class_map=np.full((120, 120), 3, dtype=np.uint8),
        confidence_map=np.full((120, 120), 0.95, dtype=np.float32),
        id_to_label={3: "floor"},
    )

    result = analyze_corridors([], settings, segmentation)

    assert result.preferred == CorridorChoice.CENTRE
    assert result.floor_extents.centre_cost == 1.0
    assert len(result.safe_polygons) == 1
    assert result.uncertain_choices == frozenset()


def test_confident_wall_across_all_corridors_is_a_dead_end() -> None:
    settings = Settings(_env_file=None)
    segmentation = SegmentationFrame(
        class_map=np.full((120, 120), 3, dtype=np.uint8),
        confidence_map=np.full((120, 120), 0.95, dtype=np.float32),
        id_to_label={3: "wall"},
    )

    result = analyze_corridors([], settings, segmentation)

    assert result.wall_dead_end is True
    assert result.floor_extents.centre_cost == 0.0
    assert result.wall_ratios.left_cost == 1.0
    assert result.wall_ratios.centre_cost == 1.0
    assert result.wall_ratios.right_cost == 1.0


def test_side_wall_is_not_misclassified_as_a_dead_end() -> None:
    settings = Settings(_env_file=None)
    class_map = np.full((120, 120), 1, dtype=np.uint8)
    class_map[:, :48] = 3
    segmentation = SegmentationFrame(
        class_map=class_map,
        confidence_map=np.full((120, 120), 0.95, dtype=np.float32),
        id_to_label={1: "sidewalk", 3: "wall"},
    )

    result = analyze_corridors([], settings, segmentation)

    assert result.wall_ratios.left_cost > result.wall_ratios.right_cost
    assert result.wall_dead_end is False


def test_stairs_are_tracked_as_hazard_surface_evidence() -> None:
    settings = Settings(_env_file=None)
    segmentation = SegmentationFrame(
        class_map=np.full((120, 120), 53, dtype=np.uint8),
        confidence_map=np.full((120, 120), 0.95, dtype=np.float32),
        id_to_label={53: "stairs, steps"},
    )

    result = analyze_corridors([], settings, segmentation)

    assert result.stairs_ratios.centre_cost == 1.0
    assert result.floor_extents.centre_cost == 0.0


def test_floor_extent_median_ignores_narrow_occluding_leg() -> None:
    settings = Settings(_env_file=None)
    class_map = np.full((120, 120), 3, dtype=np.uint8)
    class_map[70:, 58:62] = 0
    segmentation = SegmentationFrame(
        class_map=class_map,
        confidence_map=np.full((120, 120), 0.95, dtype=np.float32),
        id_to_label={0: "wall", 3: "floor"},
    )

    result = analyze_corridors([], settings, segmentation)

    assert result.floor_extents.centre_cost > 0.95
    assert result.wall_dead_end is False


def test_low_confidence_wall_is_not_claimed_as_a_dead_end() -> None:
    settings = Settings(_env_file=None)
    segmentation = SegmentationFrame(
        class_map=np.full((120, 120), 3, dtype=np.uint8),
        confidence_map=np.full((120, 120), 0.30, dtype=np.float32),
        id_to_label={3: "wall"},
    )

    result = analyze_corridors([], settings, segmentation)

    assert result.wall_dead_end is False
    assert result.wall_ratios.centre_cost == 0.0
