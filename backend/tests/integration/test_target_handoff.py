from __future__ import annotations

import base64
import io
from datetime import UTC, datetime

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.models import Base
from app.explore.local_vlm import VLMLocationResult
from app.main import create_app
from app.perception.detector import DetectionCandidate
from conftest import (
    ReadyTestDetector,
    ReadyTestOCR,
    ReadyTestSegmenter,
    ReadyTestVLM,
)


class FakeTracker:
    def __init__(self) -> None:
        self.box = (0.0, 0.0, 1.0, 1.0)

    def init(self, _image: np.ndarray, box: tuple[int, int, int, int]) -> bool:
        self.box = tuple(float(value) for value in box)
        return True

    def update(self, _image: np.ndarray):
        return True, self.box


class RecordingVLM(ReadyTestVLM):
    def __init__(self) -> None:
        super().__init__()
        self.located_shape: tuple[int, ...] | None = None

    def locate(self, image: np.ndarray, _target_name: str) -> VLMLocationResult:
        self.call_count += 1
        self.located_shape = image.shape
        return VLMLocationResult(
            box=(0.20, 0.30, 0.50, 0.80),
            point=(0.35, 0.55),
            confidence=None,
            load_ms=1.0,
            inference_ms=2.0,
            unload_ms=0.5,
        )


def jpeg_bytes() -> bytes:
    image = np.zeros((180, 320, 3), dtype=np.uint8)
    image[54:144, 64:160] = (0, 180, 255)
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    return encoded.tobytes()


def analyze(client: TestClient, session_id: str, frame_id: int):
    return client.post(
        "/api/v1/walk/analyze",
        data={
            "session_id": session_id,
            "frame_id": str(frame_id),
            "captured_at": datetime.now(UTC).isoformat(),
            "rotation_degrees": "0",
            "heading_degrees": "90",
        },
        files={"frame": ("walk.jpg", io.BytesIO(jpeg_bytes()), "image/jpeg")},
    )


def make_client(
    settings: Settings,
    vlm: RecordingVLM,
    detector: ReadyTestDetector | None = None,
) -> tuple[object, TestClient]:
    app = create_app(
        settings,
        detector_override=detector or ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=ReadyTestOCR(),
        vlm_override=vlm,
    )
    Base.metadata.create_all(app.state.database_engine)
    return app, TestClient(app)


def test_locate_uses_locked_current_walk_frame_and_initializes_tracker(
    settings: Settings,
) -> None:
    vlm = RecordingVLM()
    app, test_client = make_client(settings, vlm)
    with test_client as client:
        session_id = client.post("/api/v1/walk/sessions", json={}).json()["session_id"]
        assert analyze(client, session_id, 7).status_code == 200

        response = client.post(
            "/api/v1/vlm/locate",
            params={"target_name": "registration desk", "session_id": session_id},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "o'clock" not in payload["text"]
    assert payload["target"] == {
        "label": "registration desk",
        "confidence": None,
        "box": {"x_min": 0.2, "y_min": 0.3, "x_max": 0.5, "y_max": 0.8},
        "point": {"x": 0.35, "y": 0.55},
    }
    assert payload["tracking_allowed"] is True
    assert payload["resolved_from"] == "VLM"
    assert payload["range_hint"] == "MID"
    assert payload["bearing_degrees"] is not None
    assert payload["source_frame_id"] == 7
    assert vlm.located_shape == (180, 320, 3)
    assert payload["clock_direction"] == "11 o'clock"


def test_safety_guidance_preempts_locked_target_and_websocket_matches(
    settings: Settings,
) -> None:
    detector = ReadyTestDetector(
        [
            DetectionCandidate(
                label="bus",
                confidence=0.99,
                x1=0.43,
                y1=0.45,
                x2=0.57,
                y2=0.80,
            )
        ]
    )
    app, test_client = make_client(settings, RecordingVLM(), detector)
    with test_client as client:
        session_id = client.post("/api/v1/walk/sessions", json={}).json()["session_id"]
        assert analyze(client, session_id, 0).status_code == 200
        located = client.post(
            "/api/v1/vlm/locate",
            params={"target_name": "registration desk", "session_id": session_id},
        )
        assert located.status_code == 200, located.text
        detector.detections = [
            DetectionCandidate(
                label="bus",
                confidence=0.99,
                x1=0.34,
                y1=0.28,
                x2=0.66,
                y2=0.98,
            )
        ]

        with client.websocket_connect(
            f"/api/v1/walk/sessions/{session_id}/telemetry"
        ) as websocket:
            frame = analyze(client, session_id, 1)
            event = websocket.receive_json()

    assert frame.status_code == 200, frame.text
    payload = frame.json()
    assert payload["guidance"]["action"] == "STOP"
    assert payload["target_tracking"]["tracking_state"] == "GUIDING"
    assert payload["target_tracking"]["is_safety_overridden"] is True
    assert payload["target_tracking"]["speak"] is False
    assert payload["target_tracking"]["speech"] == ""
    assert payload["target_tracking"]["haptic_pattern"] == "NONE"
    assert event["session_id"] == session_id
    assert event["frame_id"] == 1
    assert event["tracking_state"] == "GUIDING"
    assert event["is_safety_overridden"] is True


def test_locate_accepts_explicit_snapshot_without_enabling_tracking(
    settings: Settings,
) -> None:
    _app, test_client = make_client(settings, RecordingVLM())
    with test_client as client:
        response = client.post(
            "/api/v1/vlm/locate",
            params={"target_name": "exit sign"},
            files={"frame": ("snapshot.jpg", io.BytesIO(jpeg_bytes()), "image/jpeg")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["tracking_allowed"] is False
    assert response.json()["source_frame_id"] is None


def test_recent_detector_landmark_bypasses_vlm(settings: Settings) -> None:
    detector = ReadyTestDetector(
        [
            DetectionCandidate(
                label="chair",
                confidence=0.92,
                x1=0.10,
                y1=0.25,
                x2=0.30,
                y2=0.70,
            )
        ]
    )
    vlm = RecordingVLM()
    app, test_client = make_client(settings, vlm, detector)
    with test_client as client:
        session_id = client.post("/api/v1/walk/sessions", json={}).json()["session_id"]
        assert analyze(client, session_id, 2).status_code == 200
        response = client.post(
            "/api/v1/vlm/locate",
            params={"target_name": "the chair", "session_id": session_id},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["resolved_from"] == "MEMORY"
        assert payload["tracking_allowed"] is True
        assert payload["timings"]["inference_ms"] == 0
        assert vlm.call_count == 0

        ended = client.patch(f"/api/v1/walk/sessions/{session_id}/end")
        assert ended.status_code == 200

    assert app.state.landmark_memories.count(session_id, now_ms=10_000) == 0


def test_locate_accepts_base64_snapshot(settings: Settings) -> None:
    _app, test_client = make_client(settings, RecordingVLM())
    encoded = base64.b64encode(jpeg_bytes()).decode("ascii")
    with test_client as client:
        response = client.post(
            "/api/v1/vlm/locate",
            params={"target_name": "empty chair"},
            data={"image_base64": f"data:image/jpeg;base64,{encoded}"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["target"]["label"] == "empty chair"
    assert response.json()["tracking_allowed"] is False
