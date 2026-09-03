from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.models import Base
from app.explore.ocr import OCRResult, UnavailableOCRReader
from app.main import create_app
from conftest import ReadyTestDetector, ReadyTestOCR, ReadyTestSegmenter


def jpeg_bytes(width: int = 320, height: int = 160) -> bytes:
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(
        image,
        "BUS 42A CENTRAL",
        (12, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def post_explore(client: TestClient, image: bytes | None = None, **data):
    fields = {"mode": "READ_TEXT", "preferred_language": "en-IN", **data}
    return client.post(
        "/api/v1/explore",
        data=fields,
        files={"frame": ("sign.jpg", io.BytesIO(image or jpeg_bytes()), "image/jpeg")},
    )


def test_read_text_returns_typed_high_confidence_route_result(
    client: TestClient,
) -> None:
    response = post_explore(client)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "schema_version": "1.0.0",
        "server_time": response.json()["server_time"],
        "mode": "READ_TEXT",
        "language": "eng",
        "text": "BUS 42A CENTRAL STATION",
        "route_numbers": ["42A"],
        "confidence": 0.92,
        "confidence_qualification": "HIGH",
        "message": "BUS 42A CENTRAL STATION",
        "no_text_found": False,
        "timings": response.json()["timings"],
    }
    assert all(value >= 0 for value in response.json()["timings"].values())


def test_low_confidence_and_no_text_are_explicit(client: TestClient) -> None:
    reader = client.app.state.ocr_reader
    reader.result = OCRResult("ROUTE 17", 0.41)
    low = post_explore(client)
    assert low.json()["confidence_qualification"] == "LOW"
    assert low.json()["message"] == "Possible text: ROUTE 17"
    assert low.json()["route_numbers"] == ["17"]

    reader.result = OCRResult("", 0.8)
    empty = post_explore(client)
    assert empty.json()["confidence_qualification"] == "NONE"
    assert empty.json()["confidence"] == 0
    assert empty.json()["text"] == ""
    assert empty.json()["route_numbers"] == []
    assert empty.json()["message"] == "No text found."
    assert empty.json()["no_text_found"] is True


def test_invalid_inputs_use_stable_errors(client: TestClient, settings: Settings) -> None:
    unavailable_mode = post_explore(client, mode="QUESTION")
    assert unavailable_mode.status_code == 422
    assert unavailable_mode.json()["error"]["code"] == "INVALID_REQUEST"

    unsupported_language = post_explore(client, preferred_language="hi-IN")
    assert unsupported_language.status_code == 422
    assert unsupported_language.json()["error"]["code"] == "INVALID_REQUEST"

    wrong_type = client.post(
        "/api/v1/explore",
        data={"mode": "READ_TEXT"},
        files={"frame": ("sign.png", io.BytesIO(b"png"), "image/png")},
    )
    assert wrong_type.status_code == 415
    assert wrong_type.json()["error"]["code"] == "INVALID_CONTENT_TYPE"

    malformed = post_explore(client, b"not-a-jpeg")
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "IMAGE_DECODE_FAILED"

    oversized_settings = settings.model_copy(
        update={"explore_max_image_bytes": 1024}
    )
    app = create_app(
        oversized_settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=ReadyTestOCR(),
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as limited:
        oversized = post_explore(limited, b"x" * 1025)
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_explore_frame_is_never_persisted(
    client: TestClient, tmp_path: Path
) -> None:
    assert post_explore(client).status_code == 200
    created = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert created <= {"data/drishti.db", "logs/drishti.log"}


def test_unavailable_ocr_does_not_disable_walk_mode(settings: Settings) -> None:
    app = create_app(
        settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=UnavailableOCRReader("Tesseract missing."),
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client:
        failed = post_explore(client)
        health = client.get("/api/v1/health")
        walk = client.post("/api/v1/walk/sessions", json={})
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "MODEL_NOT_READY"
    assert health.json()["models"]["ocr"]["status"] == "UNAVAILABLE"
    assert health.json()["walk_mode_available"] is True
    assert walk.status_code == 201


def test_active_ocr_rejects_another_explore_request_but_not_walk(
    settings: Settings,
) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingOCR(ReadyTestOCR):
        def read_text(self, _image: np.ndarray) -> OCRResult:
            started.set()
            release.wait(timeout=5)
            return OCRResult("BUS 42A", 0.9)

    app = create_app(
        settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=BlockingOCR(),
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(post_explore, client)
        assert started.wait(timeout=5)
        walk = client.post("/api/v1/walk/sessions", json={})
        walk_session = walk.json()
        walk_analysis = client.post(
            "/api/v1/walk/analyze",
            data={
                "session_id": walk_session["session_id"],
                "frame_id": "0",
                "captured_at": datetime.now(UTC).isoformat(),
                "rotation_degrees": "0",
            },
            files={
                "frame": (
                    "walk.jpg",
                    io.BytesIO(jpeg_bytes()),
                    "image/jpeg",
                )
            },
        )
        busy = post_explore(client)
        release.set()
        completed = first.result(timeout=5)
    assert walk.status_code == 201
    assert walk_analysis.status_code == 200
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "CONFLICT"
    assert completed.status_code == 200
