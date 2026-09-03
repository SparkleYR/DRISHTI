from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from app.perception.detector import DetectionCandidate
from app.perception.segmenter import SegmentationFrame
from test_walk import analyze, start_session


class AllWallSegmenter:
    ready = True
    detail = "Controlled confident wall fixture."

    def segment(self, image: np.ndarray) -> SegmentationFrame:
        height, width = image.shape[:2]
        return SegmentationFrame(
            class_map=np.full((height, width), 3, dtype=np.uint8),
            confidence_map=np.full((height, width), 0.95, dtype=np.float32),
            id_to_label={3: "wall"},
        )


class ClearHallSegmenter:
    ready = True
    detail = "Controlled clear hall fixture."

    def segment(self, image: np.ndarray) -> SegmentationFrame:
        height, width = image.shape[:2]
        return SegmentationFrame(
            class_map=np.full((height, width), 1, dtype=np.uint8),
            confidence_map=np.full((height, width), 0.95, dtype=np.float32),
            id_to_label={1: "sidewalk"},
        )


def test_wall_ahead_uses_stable_stop_and_existing_contract(
    client: TestClient,
) -> None:
    client.app.state.segmenter = AllWallSegmenter()
    session_id = str(start_session(client)["session_id"])

    pending = analyze(client, session_id, frame_id=0).json()
    stopped = analyze(client, session_id, frame_id=1).json()

    assert pending["guidance"]["reason_code"] == "ALERT_PERSISTENCE_PENDING"
    assert stopped["guidance"] == {
        "level": "HIGH",
        "action": "STOP",
        "speech": "Stop. Obstacle directly ahead.",
        "haptic_pattern": "CRITICAL_RAPID",
        "speak": True,
        "reason_code": "WALL_OR_DEAD_END_AHEAD",
    }
    assert stopped["overlay"]["preferred_corridor"] == "NONE"
    assert stopped["overlay"]["direction_arrow"] == "STOP"
    assert len(stopped["overlay"]["blocked_polygons"]) == 3
    assert "india_hazards" not in stopped["degraded_modules"]


def test_clear_hall_has_no_false_wall_stop(client: TestClient) -> None:
    client.app.state.segmenter = ClearHallSegmenter()
    session_id = str(start_session(client)["session_id"])

    results = [analyze(client, session_id, frame_id=index).json() for index in range(3)]

    assert all(item["guidance"]["action"] == "CLEAR" for item in results)
    assert all(
        item["guidance"]["reason_code"] != "WALL_OR_DEAD_END_AHEAD"
        for item in results
    )


def test_desk_uses_generic_tracking_spatial_and_risk_pipeline(
    client: TestClient,
) -> None:
    client.app.state.segmenter = ClearHallSegmenter()
    client.app.state.detector.detections = [
        DetectionCandidate("desk", 0.91, 0.34, 0.45, 0.66, 0.96)
    ]
    session_id = str(start_session(client)["session_id"])

    first = analyze(client, session_id, frame_id=0).json()
    second = analyze(client, session_id, frame_id=1).json()

    assert first["detections"][0]["label"] == "desk"
    assert second["detections"][0]["track_id"] == first["detections"][0]["track_id"]
    assert second["detections"][0]["direction"] == "CENTRE"
    assert second["detections"][0]["path_overlap"] > 0.5
    assert second["guidance"]["action"] in {
        "STOP",
        "MOVE_LEFT",
        "MOVE_RIGHT",
        "PAUSE_UNCLEAR",
    }
    assert second["guidance"]["action"] != "CLEAR"
