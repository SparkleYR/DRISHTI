import pytest

from app.perception.detector import RawDetection, canonicalize_detections


def test_canonicalizes_supported_classes_and_normalizes_boxes() -> None:
    result = canonicalize_detections(
        [
            RawDetection("person", 0.9, 10, 20, 60, 90),
            RawDetection("backpack", 0.8, 20, 10, 40, 50),
            RawDetection("handbag", 0.7, 0, 0, 20, 20),
            RawDetection("dining table", 0.85, 5, 30, 95, 95),
        ],
        width=100,
        height=100,
        confidence_threshold=0.35,
    )

    assert [item.label for item in result] == ["person", "bag", "bag", "desk"]
    assert (result[0].x1, result[0].y1, result[0].x2, result[0].y2) == (
        0.1,
        0.2,
        0.6,
        0.9,
    )


@pytest.mark.parametrize(
    "label",
    [
        "person", "chair", "desk", "bicycle", "motorcycle", "car", "bus", "bench",
        "door", "suitcase", "umbrella", "potted plant", "couch", "bed", "tv",
        "refrigerator", "sink", "toilet",
    ],
)
def test_keeps_every_supported_coco_demonstration_class(label: str) -> None:
    result = canonicalize_detections(
        [RawDetection(label, 0.5, 1, 1, 9, 9)],
        width=10,
        height=10,
        confidence_threshold=0.35,
    )
    assert result[0].label == label


def test_filters_irrelevant_low_confidence_and_degenerate_detections() -> None:
    result = canonicalize_detections(
        [
            RawDetection("dog", 0.99, 1, 1, 9, 9),
            RawDetection("chair", 0.34, 1, 1, 9, 9),
            RawDetection("car", 0.8, 9, 1, 1, 9),
            RawDetection("person", float("nan"), 1, 1, 9, 9),
        ],
        width=10,
        height=10,
        confidence_threshold=0.35,
    )
    assert result == []


def test_maps_generic_table_alias_to_the_hall_desk_contract_label() -> None:
    result = canonicalize_detections(
        [RawDetection("table", 0.75, 1, 1, 9, 9)],
        width=10,
        height=10,
        confidence_threshold=0.35,
    )

    assert [item.label for item in result] == ["desk"]


def test_clamps_model_rounding_at_image_edges() -> None:
    result = canonicalize_detections(
        [RawDetection("bus", 1.00001, -0.1, -0.2, 100.1, 50.2)],
        width=100,
        height=50,
        confidence_threshold=0.35,
    )
    assert (result[0].confidence, result[0].x1, result[0].y1) == (1.0, 0.0, 0.0)
    assert (result[0].x2, result[0].y2) == (1.0, 1.0)


def test_rejects_invalid_image_dimensions() -> None:
    with pytest.raises(ValueError, match="positive"):
        canonicalize_detections([], width=0, height=10, confidence_threshold=0.35)
