from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np

from app.perception.segmenter import SegmentationFrame
from app.schemas.walk import NormalizedPoint, SurfaceKind, SurfaceRegion


NON_WALKABLE_LABELS = frozenset(
    {
        "building",
        "wall",
        "fence",
        "pole",
        "traffic light",
        "traffic sign",
        "vegetation",
        "person",
        "rider",
        "car",
        "truck",
        "bus",
        "train",
        "motorcycle",
        "bicycle",
    }
)


def semantic_kind_map(segmentation: SegmentationFrame) -> np.ndarray:
    kinds = np.full(segmentation.class_map.shape, _kind_code(SurfaceKind.UNKNOWN), dtype=np.uint8)
    for class_id, label in segmentation.id_to_label.items():
        if label == "sidewalk":
            kind = SurfaceKind.WALKABLE
        elif label == "road":
            kind = SurfaceKind.ROAD
        elif label in NON_WALKABLE_LABELS:
            kind = SurfaceKind.NON_WALKABLE
        else:
            kind = SurfaceKind.UNKNOWN
        kinds[segmentation.class_map == class_id] = _kind_code(kind)
    return kinds


def extract_surface_regions(
    segmentation: SegmentationFrame,
    *,
    frame_id: int,
) -> list[SurfaceRegion]:
    kind_map = semantic_kind_map(segmentation)
    regions: list[SurfaceRegion] = []
    for kind in SurfaceKind:
        mask = (kind_map == _kind_code(kind)).astype(np.uint8)
        regions.extend(
            _regions_for_mask(
                mask,
                segmentation.confidence_map,
                kind=kind,
                frame_id=frame_id,
            )
        )
    return sorted(regions, key=lambda region: region.confidence, reverse=True)[:16]


def _regions_for_mask(
    mask: np.ndarray,
    confidence_map: np.ndarray,
    *,
    kind: SurfaceKind,
    frame_id: int,
) -> Iterable[SurfaceRegion]:
    height, width = mask.shape
    minimum_area = max(32.0, height * width * 0.0025)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:4]
    for contour in contours:
        if cv2.contourArea(contour) < minimum_area:
            continue
        perimeter = cv2.arcLength(contour, True)
        simplified = cv2.approxPolyDP(contour, max(1.0, perimeter * 0.01), True)
        points = simplified.reshape(-1, 2)
        if len(points) > 64:
            indices = np.linspace(0, len(points) - 1, 64, dtype=int)
            points = points[indices]
        if len(points) < 3:
            continue

        region_mask = np.zeros_like(mask)
        cv2.drawContours(region_mask, [contour], -1, color=1, thickness=cv2.FILLED)
        values = confidence_map[(region_mask == 1) & (mask == 1)]
        confidence = float(np.mean(values)) if values.size else 0.0
        yield SurfaceRegion(
            kind=kind,
            confidence=min(1.0, max(0.0, confidence)),
            polygon=[
                NormalizedPoint(
                    x=float(x) / max(1, width - 1),
                    y=float(y) / max(1, height - 1),
                )
                for x, y in points
            ],
            source_frame_id=frame_id,
        )


def _kind_code(kind: SurfaceKind) -> int:
    return list(SurfaceKind).index(kind)
