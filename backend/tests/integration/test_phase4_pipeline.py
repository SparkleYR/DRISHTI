from __future__ import annotations

import json

import numpy as np
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT
from app.perception.detector import DetectionCandidate
from app.perception.segmenter import SegmentationFrame
from test_walk import analyze


class AllWalkableSegmenter:
    ready = True
    detail = "Controlled all-walkable test surface."

    def segment(self, image: np.ndarray) -> SegmentationFrame:
        height, width = image.shape[:2]
        return SegmentationFrame(
            class_map=np.ones((height, width), dtype=np.uint8),
            confidence_map=np.full((height, width), 0.95, dtype=np.float32),
            id_to_label={1: "sidewalk"},
        )


SCENARIOS = json.loads(
    (PROJECT_ROOT / "test-media" / "phase4" / "decision-scenarios.json").read_text()
)["scenarios"]


def candidates(name: str) -> list[DetectionCandidate]:
    return [
        DetectionCandidate(item["label"], item["confidence"], *item["bbox"])
        for item in SCENARIOS[name]
    ]


def start(client: TestClient, *, haptics_enabled: bool = True) -> str:
    response = client.post(
        "/api/v1/walk/sessions",
        json={
            "device_alias": "phase-4-integration",
            "settings": {"haptics_enabled": haptics_enabled},
        },
    )
    assert response.status_code == 201
    return str(response.json()["session_id"])


def test_chair_centre_left_blocked_selects_right_repeatedly(
    client: TestClient,
) -> None:
    client.app.state.segmenter = AllWalkableSegmenter()
    detector = client.app.state.detector

    for _ in range(3):
        session_id = start(client)
        detector.detections = candidates("chair_centre_left_blocked")
        first = analyze(client, session_id, frame_id=0)
        second = analyze(client, session_id, frame_id=1)
        assert first.status_code == second.status_code == 200
        assert first.json()["guidance"]["reason_code"] == "ALERT_PERSISTENCE_PENDING"
        payload = second.json()
        assert payload["guidance"] == {
            "level": "HIGH",
            "action": "MOVE_RIGHT",
            "speech": "Path blocked. Move slightly right.",
            "haptic_pattern": "WARNING_DOUBLE",
            "speak": True,
            "reason_code": "CENTRE_BLOCKED_CLEARER_SIDE",
        }
        assert payload["overlay"]["preferred_corridor"] == "RIGHT"
        assert payload["overlay"]["direction_arrow"] == "RIGHT"
        assert len(payload["overlay"]["safe_polygons"]) == 1
        assert len(payload["overlay"]["blocked_polygons"]) >= 1
        assert payload["timings"]["risk_ms"] >= 0


def test_centre_right_blocked_selects_left(client: TestClient) -> None:
    client.app.state.segmenter = AllWalkableSegmenter()
    detector = client.app.state.detector
    detector.detections = candidates("chair_centre_right_blocked")
    session_id = start(client)

    analyze(client, session_id, frame_id=0)
    response = analyze(client, session_id, frame_id=1)

    assert response.json()["guidance"]["action"] == "MOVE_LEFT"
    assert response.json()["overlay"]["preferred_corridor"] == "LEFT"
    assert response.json()["overlay"]["direction_arrow"] == "LEFT"


def test_all_corridors_blocked_produces_stop(client: TestClient) -> None:
    client.app.state.segmenter = AllWalkableSegmenter()
    client.app.state.detector.detections = candidates("all_corridors_blocked")

    response = analyze(client, start(client), frame_id=0)
    payload = response.json()

    assert payload["guidance"]["action"] == "STOP"
    assert payload["guidance"]["level"] == "CRITICAL"
    assert payload["guidance"]["haptic_pattern"] == "CRITICAL_RAPID"
    assert payload["overlay"]["preferred_corridor"] == "NONE"
    assert payload["overlay"]["safe_polygons"] == []
    assert payload["overlay"]["direction_arrow"] == "STOP"


def test_side_only_low_risk_object_remains_silent(client: TestClient) -> None:
    client.app.state.segmenter = AllWalkableSegmenter()
    client.app.state.detector.detections = [
        DetectionCandidate("bag", 0.50, 0.01, 0.35, 0.12, 0.70)
    ]

    response = analyze(client, start(client), frame_id=0)
    payload = response.json()

    assert payload["guidance"]["action"] == "CLEAR"
    assert payload["guidance"]["speech"] == ""
    assert payload["guidance"]["speak"] is False
    assert payload["overlay"]["preferred_corridor"] == "CENTRE"
    assert payload["overlay"]["direction_arrow"] == "NONE"


def test_unchanged_guidance_is_deduplicated(client: TestClient) -> None:
    client.app.state.segmenter = AllWalkableSegmenter()
    client.app.state.detector.detections = candidates("chair_centre_left_blocked")
    session_id = start(client)

    analyze(client, session_id, frame_id=0)
    announced = analyze(client, session_id, frame_id=1).json()
    duplicate = analyze(client, session_id, frame_id=2).json()

    assert announced["guidance"]["action"] == "MOVE_RIGHT"
    assert announced["guidance"]["speak"] is True
    assert duplicate["guidance"]["action"] == "MOVE_RIGHT"
    assert duplicate["guidance"]["speak"] is False


def test_critical_approaching_vehicle_interrupts_cooldown(client: TestClient) -> None:
    detector = client.app.state.detector
    session_id = start(client)
    detector.detections = [
        DetectionCandidate("motorcycle", 0.95, 0.43, 0.45, 0.57, 0.80)
    ]
    first = analyze(client, session_id, frame_id=0).json()
    client.app.state.segmenter = AllWalkableSegmenter()
    detector.detections = [
        DetectionCandidate("motorcycle", 0.95, 0.34, 0.28, 0.66, 0.98)
    ]

    second = analyze(client, session_id, frame_id=1).json()

    assert first["guidance"]["action"] == "PAUSE_UNCLEAR"
    assert first["guidance"]["speak"] is True
    assert second["guidance"]["action"] == "STOP"
    assert second["guidance"]["reason_code"] == "APPROACHING_VEHICLE_CENTRE"
    assert second["guidance"]["speak"] is True
    assert second["detections"][0]["risk_level"] == "CRITICAL"
    assert second["detections"][0]["display_color"] == "RED"


def test_haptic_preference_preserves_action_but_disables_pattern(
    client: TestClient,
) -> None:
    response = analyze(
        client,
        start(client, haptics_enabled=False),
        frame_id=0,
    )

    assert response.json()["guidance"]["action"] == "PAUSE_UNCLEAR"
    assert response.json()["guidance"]["haptic_pattern"] == "NONE"
