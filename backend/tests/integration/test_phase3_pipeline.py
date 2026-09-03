import json

from fastapi.testclient import TestClient
import numpy as np

from app.config import PROJECT_ROOT
from app.perception.detector import DetectionCandidate
from app.perception.segmenter import SegmentationFrame, UnavailableSegmenter
from conftest import ReadyTestSegmenter
from test_walk import analyze, start_session


def test_two_frames_keep_track_and_detect_approach(client: TestClient) -> None:
    detector = client.app.state.detector
    session = start_session(client)
    session_id = str(session["session_id"])
    fixture = json.loads(
        (PROJECT_ROOT / "test-media" / "phase3" / "approaching-vehicle.json").read_text()
    )
    first_box = fixture["frames"][0]
    second_box = fixture["frames"][1]
    detector.detections = [
        DetectionCandidate(
            fixture["label"],
            first_box["confidence"],
            *first_box["bbox"],
        )
    ]
    first = analyze(client, session_id, frame_id=0)
    detector.detections = [
        DetectionCandidate(
            fixture["label"],
            second_box["confidence"],
            *second_box["bbox"],
        )
    ]
    second = analyze(client, session_id, frame_id=1)

    assert first.status_code == second.status_code == 200
    first_detection = first.json()["detections"][0]
    second_detection = second.json()["detections"][0]
    assert first_detection["track_id"] == second_detection["track_id"]
    assert second_detection["approach_state"] == "APPROACHING"
    assert second_detection["approach_rate"] > 0
    assert second_detection["motion_vector"] is not None
    assert second_detection["proximity_score"] > first_detection["proximity_score"]


def test_segmentation_surface_contract_is_frame_scoped(client: TestClient) -> None:
    class HalfSidewalkSegmenter(ReadyTestSegmenter):
        def segment(self, image: np.ndarray) -> SegmentationFrame:
            height, width = image.shape[:2]
            classes = np.full((height, width), 10, dtype=np.uint8)
            classes[height // 2 :, :] = 1
            return SegmentationFrame(
                class_map=classes,
                confidence_map=np.full((height, width), 0.9, dtype=np.float32),
                id_to_label={1: "sidewalk", 10: "sky"},
            )

    client.app.state.segmenter = HalfSidewalkSegmenter()
    session = start_session(client)
    response = analyze(client, str(session["session_id"]), frame_id=9)

    assert response.status_code == 200
    payload = response.json()
    assert {region["kind"] for region in payload["surfaces"]} == {
        "WALKABLE",
        "UNKNOWN",
    }
    assert all(region["source_frame_id"] == 9 for region in payload["surfaces"])
    assert "segmentation" not in payload["degraded_modules"]


def test_segmentation_failure_uses_uncertain_geometric_fallback(
    client: TestClient,
) -> None:
    client.app.state.segmenter = UnavailableSegmenter("Test model unavailable.")
    health = client.get("/api/v1/health")
    session = start_session(client)
    response = analyze(client, str(session["session_id"]), frame_id=0)

    assert response.status_code == 200
    assert health.json()["walk_mode_available"] is True
    assert health.json()["models"]["segmentation"]["status"] == "UNAVAILABLE"
    assert health.json()["models"]["india_hazards"]["status"] == "DEGRADED"
    payload = response.json()
    assert payload["surfaces"] == []
    assert len(payload["overlay"]["uncertain_polygons"]) == 3
    assert "segmentation" in payload["degraded_modules"]
    assert "india_hazards" in payload["degraded_modules"]
    assert "detector" not in payload["degraded_modules"]
    assert payload["guidance"]["action"] == "PAUSE_UNCLEAR"
