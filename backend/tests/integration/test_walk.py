from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
from fastapi.testclient import TestClient
import numpy as np

from app.config import Settings
from app.main import create_app
from app.perception.detector import DetectionCandidate, UnavailableDetector
from app.perception.segmenter import UnavailableSegmenter

from conftest import ReadyTestDetector, ReadyTestSegmenter


def jpeg_bytes(width: int = 32, height: int = 24) -> bytes:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 1] = 180
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    return encoded.tobytes()


def start_session(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/walk/sessions",
        json={"device_alias": "integration-test"},
    )
    assert response.status_code == 201
    return response.json()


def analyze(
    client: TestClient,
    session_id: str,
    *,
    frame_id: int = 0,
    payload: bytes | None = None,
    content_type: str = "image/jpeg",
    captured_at: datetime | None = None,
    rotation_degrees: int = 0,
):
    return client.post(
        "/api/v1/walk/analyze",
        data={
            "session_id": session_id,
            "frame_id": str(frame_id),
            "captured_at": (captured_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
            "rotation_degrees": str(rotation_degrees),
        },
        files={"frame": ("frame.jpg", payload if payload is not None else jpeg_bytes(), content_type)},
    )


def test_start_session_matches_contract(client: TestClient, settings: Settings) -> None:
    payload = start_session(client)

    assert payload["schema_version"] == "1.0.0"
    assert isinstance(payload["session_id"], str)
    assert payload["recommended_capture_fps"] == settings.recommended_capture_fps
    assert payload["max_image_width"] == settings.max_image_width
    assert payload["max_image_bytes"] == settings.max_image_bytes
    assert payload["max_result_age_ms"] == settings.max_result_age_ms
    assert str(payload["server_time"]).endswith("Z")
    assert str(payload["started_at"]).endswith("Z")


def test_analyze_echoes_fresh_frame_and_uncertain_guidance(client: TestClient) -> None:
    session = start_session(client)
    response = analyze(client, str(session["session_id"]), frame_id=7)

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["session_id"] == session["session_id"]
    assert payload["frame_id"] == 7
    assert payload["geometry"] == {
        "coordinate_space": "ORIENTED_CAPTURE_NORMALIZED",
        "source_width": 32,
        "source_height": 24,
        "rotation_degrees": 0,
        "mirrored": False,
    }
    assert payload["detections"] == []
    assert payload["surfaces"][0]["kind"] == "UNKNOWN"
    assert payload["surfaces"][0]["source_frame_id"] == 7
    assert payload["overlay"]["preferred_corridor"] == "NONE"
    assert payload["overlay"]["safe_polygons"] == []
    assert payload["overlay"]["blocked_polygons"] == []
    assert len(payload["overlay"]["uncertain_polygons"]) == 3
    assert payload["guidance"]["action"] == "PAUSE_UNCLEAR"
    assert payload["guidance"]["level"] == "WARN"
    assert payload["guidance"]["speech"] == "Path unclear. Please pause."
    assert payload["guidance"]["haptic_pattern"] == "UNCLEAR_LONG"
    assert payload["guidance"]["speak"] is True
    assert payload["guidance"]["reason_code"] == "CENTRE_SURFACE_UNCERTAIN"
    assert payload["timings"]["decode_ms"] >= 0
    assert payload["timings"]["segmentation_ms"] >= 0
    assert payload["timings"]["tracking_depth_ms"] >= 0
    assert payload["timings"]["spatial_ms"] >= 0
    assert payload["timings"]["risk_ms"] >= 0
    assert payload["timings"]["total_ms"] >= payload["timings"]["decode_ms"]
    assert payload["frame_age_ms"] >= 0


def test_analyze_returns_normalized_detection_contract(
    client: TestClient,
) -> None:
    detector = client.app.state.detector
    detector.detections = [
        DetectionCandidate(
            label="chair",
            confidence=0.875,
            x1=0.1,
            y1=0.2,
            x2=0.6,
            y2=0.9,
        )
    ]
    session = start_session(client)

    response = analyze(client, str(session["session_id"]), frame_id=2)

    assert response.status_code == 200
    detection = response.json()["detections"][0]
    assert detection["track_id"] == 1
    assert detection["label"] == "chair"
    assert detection["confidence"] == 0.875
    assert detection["bbox"] == {"x1": 0.1, "y1": 0.2, "x2": 0.6, "y2": 0.9}
    assert detection["anchor"] == {"x": 0.35, "y": 0.9}
    assert detection["direction"] == "LEFT"
    assert detection["proximity"] == "IMMEDIATE"
    assert 0 <= detection["proximity_score"] <= 1
    assert detection["approach_state"] == "UNKNOWN"
    assert detection["approach_rate"] is None
    assert detection["motion_vector"] is None
    assert 0 < detection["path_overlap"] < 1
    assert 0 < detection["risk_score"] <= 1
    assert detection["risk_level"] == "WATCH"
    assert detection["display_color"] == "YELLOW"
    assert response.json()["timings"]["detection_ms"] >= 0
    assert "detector" not in response.json()["degraded_modules"]


def test_model_unavailable_disables_walk_mode_and_rejects_analysis(
    settings: Settings,
) -> None:
    app = create_app(
        settings,
        detector_override=UnavailableDetector("Test weights missing."),
        segmenter_override=ReadyTestSegmenter(),
    )
    with TestClient(app) as unavailable_client:
        health = unavailable_client.get("/api/v1/health")
        session = start_session(unavailable_client)
        response = analyze(unavailable_client, str(session["session_id"]))

    assert health.status_code == 200
    assert health.json()["walk_mode_available"] is False
    assert health.json()["models"]["detector"] == {
        "status": "UNAVAILABLE",
        "detail": "Test weights missing.",
    }
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_READY"
    assert response.json()["error"]["retryable"] is True


def test_core_models_are_initialized_once_per_application(
    settings: Settings, monkeypatch
) -> None:
    detector = ReadyTestDetector()
    segmenter = ReadyTestSegmenter()
    detector_loads = 0
    segmenter_loads = 0

    def load_detector_once(_settings: Settings):
        nonlocal detector_loads
        detector_loads += 1
        return detector

    def load_segmenter_once(_settings: Settings):
        nonlocal segmenter_loads
        segmenter_loads += 1
        return segmenter

    monkeypatch.setattr("app.main.load_detector", load_detector_once)
    monkeypatch.setattr("app.main.load_segmenter", load_segmenter_once)
    app = create_app(settings)
    with TestClient(app) as loaded_client:
        assert loaded_client.get("/api/v1/health").status_code == 200
        assert loaded_client.get("/api/v1/health").status_code == 200

    assert detector_loads == 1
    assert segmenter_loads == 1


def test_five_consecutive_frames_echo_matching_ids(client: TestClient) -> None:
    session = start_session(client)
    session_id = str(session["session_id"])

    responses = [analyze(client, session_id, frame_id=frame_id) for frame_id in range(5)]

    assert [response.status_code for response in responses] == [200] * 5
    assert [response.json()["session_id"] for response in responses] == [session_id] * 5
    assert [response.json()["frame_id"] for response in responses] == list(range(5))


def test_rotation_swaps_oriented_dimensions(client: TestClient) -> None:
    session = start_session(client)
    response = analyze(
        client,
        str(session["session_id"]),
        payload=jpeg_bytes(width=40, height=20),
        rotation_degrees=90,
    )

    assert response.status_code == 200
    assert response.json()["geometry"]["source_width"] == 20
    assert response.json()["geometry"]["source_height"] == 40


def test_session_end_is_idempotent_and_blocks_frames(client: TestClient) -> None:
    session = start_session(client)
    session_id = str(session["session_id"])

    first = client.patch(f"/api/v1/walk/sessions/{session_id}/end")
    second = client.patch(f"/api/v1/walk/sessions/{session_id}/end")
    rejected = analyze(client, session_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["ended_at"] == second.json()["ended_at"]
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "SESSION_ENDED"


def test_unknown_session_is_rejected(client: TestClient) -> None:
    response = analyze(client, "missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_frame_id_must_increase(client: TestClient) -> None:
    session = start_session(client)
    session_id = str(session["session_id"])
    assert analyze(client, session_id, frame_id=3).status_code == 200

    response = analyze(client, session_id, frame_id=3)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FRAME_ID_NOT_MONOTONIC"


def test_stale_frame_is_rejected_before_decode(client: TestClient, settings: Settings) -> None:
    session = start_session(client)
    old = datetime.now(UTC) - timedelta(milliseconds=settings.max_result_age_ms + 100)

    response = analyze(client, str(session["session_id"]), captured_at=old)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FRAME_TOO_OLD"
    assert response.json()["error"]["retryable"] is True


def test_far_future_capture_timestamp_is_rejected(client: TestClient) -> None:
    session = start_session(client)
    future = datetime.now(UTC) + timedelta(seconds=6)

    response = analyze(client, str(session["session_id"]), captured_at=future)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_wrong_mime_type_is_rejected(client: TestClient) -> None:
    session = start_session(client)
    response = analyze(
        client,
        str(session["session_id"]),
        content_type="image/png",
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INVALID_CONTENT_TYPE"


def test_spoofed_or_malformed_jpeg_is_rejected(client: TestClient) -> None:
    session = start_session(client)
    response = analyze(
        client,
        str(session["session_id"]),
        payload=b"\xff\xd8\xffnot-a-real-jpeg",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


def test_image_over_byte_limit_is_rejected_in_memory(client: TestClient, settings: Settings) -> None:
    session = start_session(client)
    oversized = b"\xff\xd8\xff" + b"x" * settings.max_image_bytes

    response = analyze(client, str(session["session_id"]), payload=oversized)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_request_over_total_body_limit_is_rejected(client: TestClient, settings: Settings) -> None:
    session = start_session(client)
    oversized = b"x" * (
        settings.max_image_bytes + settings.max_multipart_overhead_bytes + 1
    )

    response = analyze(client, str(session["session_id"]), payload=oversized)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_oriented_width_limit_is_enforced(client: TestClient, settings: Settings) -> None:
    session = start_session(client)
    response = analyze(
        client,
        str(session["session_id"]),
        payload=jpeg_bytes(width=settings.max_image_width + 1, height=10),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_invalid_metadata_does_not_echo_raw_input(client: TestClient) -> None:
    session = start_session(client)
    sensitive_marker = "must-not-be-echoed"
    response = client.post(
        "/api/v1/walk/analyze",
        data={
            "session_id": session["session_id"],
            "frame_id": sensitive_marker,
            "captured_at": datetime.now(UTC).isoformat(),
            "rotation_degrees": "45",
        },
        files={"frame": ("frame.jpg", jpeg_bytes(), "image/jpeg")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert sensitive_marker not in response.text


def test_frame_upload_creates_no_image_file(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    session = start_session(client)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_file()}

    response = analyze(client, str(session["session_id"]))

    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_file()}
    assert response.status_code == 200
    assert after == before
    assert after <= {Path("data/drishti.db"), Path("logs/drishti.log")}


def test_active_sessions_are_discoverable_until_they_end(client: TestClient) -> None:
    """The dashboard cannot know a runtime UUID, so it discovers one here."""
    empty = client.get("/api/v1/walk/sessions/active")
    assert empty.status_code == 200, empty.text
    assert empty.json()["sessions"] == []

    session_id = client.post("/api/v1/walk/sessions", json={}).json()["session_id"]

    listed = client.get("/api/v1/walk/sessions/active")
    assert listed.status_code == 200, listed.text
    sessions = listed.json()["sessions"]
    assert [item["session_id"] for item in sessions] == [session_id]
    assert sessions[0]["last_frame_id"] == -1
    assert sessions[0]["last_frame_at"] is None
    assert sessions[0]["last_action"] is None
    # Metadata only: no frame bytes and nothing identifying.
    assert set(sessions[0]) == {
        "session_id",
        "started_at",
        "last_frame_id",
        "last_frame_at",
        "last_action",
        "last_risk_level",
    }

    assert client.patch(f"/api/v1/walk/sessions/{session_id}/end").status_code == 200
    assert client.get("/api/v1/walk/sessions/active").json()["sessions"] == []


def test_active_path_is_not_captured_as_a_session_id(client: TestClient) -> None:
    # "active" must route to the listing, not to the {session_id} converters.
    response = client.get("/api/v1/walk/sessions/active")
    assert response.status_code == 200
    assert "sessions" in response.json()


def test_active_session_reports_liveness_after_a_frame(client: TestClient) -> None:
    """Operators need to see a device is alive and what it was last told."""
    session_id = str(start_session(client)["session_id"])
    assert analyze(client, session_id, frame_id=0).status_code == 200

    listed = client.get("/api/v1/walk/sessions/active").json()["sessions"][0]
    assert listed["last_frame_id"] == 0
    assert listed["last_frame_at"] is not None
    assert listed["last_action"] in {
        "CLEAR", "CAUTION", "MOVE_LEFT", "MOVE_RIGHT", "STOP", "PAUSE_UNCLEAR",
    }
    assert listed["last_risk_level"] in {"CLEAR", "WATCH", "WARN", "HIGH", "CRITICAL"}
