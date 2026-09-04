from __future__ import annotations

import pytest

from app.perception.detector import DetectionCandidate
from app.perception.landmark_memory import (
    LandmarkMemoryStore,
    labels_match,
    normalize_label,
)


def candidate(
    label: str,
    box: tuple[float, float, float, float] = (0.4, 0.4, 0.6, 0.7),
    confidence: float = 0.9,
) -> DetectionCandidate:
    x1, y1, x2, y2 = box
    return DetectionCandidate(
        label=label, confidence=confidence, x1=x1, y1=y1, x2=x2, y2=y2
    )


def store(**overrides) -> LandmarkMemoryStore:
    kwargs = {
        "ttl_seconds": 45,
        "max_entries": 40,
        "camera_hfov_degrees": 67.0,
        "min_confidence": 0.45,
        "min_sightings": 2,
    }
    kwargs.update(overrides)
    memory = LandmarkMemoryStore(**kwargs)
    memory.start_session("session")
    return memory


def test_full_coco_labels_are_remembered_and_resolved_by_a_spoken_query() -> None:
    memory = store()
    for now_ms in (1_000, 1_500):
        memory.observe(
            "session",
            now_ms=now_ms,
            heading_degrees=90.0,
            detections=[candidate("bottle"), candidate("cell phone")],
        )

    assert memory.resolve("session", "the blue bottle", now_ms=2_000) is not None
    assert memory.resolve("session", "my phone", now_ms=2_000) is not None


def test_confidence_floor_keeps_weak_boxes_out_of_memory() -> None:
    memory = store()
    for now_ms in (1_000, 1_500):
        memory.observe(
            "session",
            now_ms=now_ms,
            heading_degrees=None,
            detections=[candidate("bottle", confidence=0.36)],
        )

    assert memory.count("session", now_ms=2_000) == 0
    assert memory.resolve("session", "bottle", now_ms=2_000) is None


def test_sightings_gate_blocks_a_single_frame_flicker_and_admits_two() -> None:
    memory = store()
    memory.observe(
        "session", now_ms=1_000, heading_degrees=None, detections=[candidate("bottle")]
    )
    assert memory.resolve("session", "bottle", now_ms=1_200) is None

    memory.observe(
        "session", now_ms=1_500, heading_degrees=None, detections=[candidate("bottle")]
    )
    resolved = memory.resolve("session", "bottle", now_ms=2_000)
    assert resolved is not None
    assert resolved.sightings == 2


def test_first_heading_frame_adopts_the_bearingless_entry_and_keeps_sightings() -> None:
    memory = store()
    for now_ms in (1_000, 1_500):
        memory.observe(
            "session",
            now_ms=now_ms,
            heading_degrees=None,
            detections=[candidate("bottle")],
        )
    memory.observe(
        "session", now_ms=2_000, heading_degrees=90.0, detections=[candidate("bottle")]
    )

    assert memory.count("session", now_ms=2_100) == 1
    resolved = memory.resolve("session", "bottle", now_ms=2_100)
    assert resolved is not None
    assert resolved.sightings == 3
    assert resolved.world_bearing_deg == pytest.approx(90.0)


def test_vlm_confirmed_landmark_is_resolvable_without_a_second_sighting() -> None:
    memory = store()
    memory.remember(
        "session",
        label="registration desk",
        now_ms=1_000,
        heading_degrees=None,
        box=(0.2, 0.3, 0.5, 0.8),
    )
    assert memory.resolve("session", "registration desk", now_ms=1_200) is not None


def test_person_stays_out_of_memory_unless_explicitly_allowed() -> None:
    memory = store()
    for now_ms in (1_000, 1_500):
        memory.observe(
            "session",
            now_ms=now_ms,
            heading_degrees=None,
            detections=[candidate("person")],
        )
    assert memory.resolve("session", "person", now_ms=2_000) is None

    allowed = store(allow_person=True)
    for now_ms in (1_000, 1_500):
        allowed.observe(
            "session",
            now_ms=now_ms,
            heading_degrees=None,
            detections=[candidate("person")],
        )
    assert allowed.resolve("session", "person", now_ms=2_000) is not None


def test_bare_colour_word_query_still_resolves_the_coco_class() -> None:
    # "orange" is both a colour and a COCO class; stripping it would leave an
    # empty target that matches nothing.
    assert normalize_label("orange") == "orange"
    assert normalize_label("the orange bottle") == "bottle"
    assert normalize_label("a grey cell phone") == "cell phone"

    memory = store()
    for now_ms in (1_000, 1_500):
        memory.observe(
            "session",
            now_ms=now_ms,
            heading_degrees=None,
            detections=[candidate("orange")],
        )
    assert memory.resolve("session", "orange", now_ms=2_000) is not None


def test_aliased_risk_labels_stay_reachable_by_the_users_word() -> None:
    assert labels_match("backpack", "bag")
    assert labels_match("my handbag", "bag")
    assert labels_match("table", "dining table")
    assert labels_match("mug", "cup")
    assert labels_match("the remote control", "remote")
    assert not labels_match("bottle", "book")
