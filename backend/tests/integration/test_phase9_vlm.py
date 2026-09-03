from __future__ import annotations

import base64
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
from app.explore.local_vlm import UnavailableVLMEngine, VLMResult
from app.main import create_app
from conftest import ReadyTestDetector, ReadyTestOCR, ReadyTestSegmenter, ReadyTestVLM


def jpeg_bytes(width: int = 320, height: int = 180) -> bytes:
    image = np.full((height, width, 3), 230, dtype=np.uint8)
    cv2.rectangle(image, (80, 40), (240, 150), (0, 0, 0), 4)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def post_vlm(client: TestClient, **data):
    prompt = data.pop("prompt", "What is in front of me?")
    image = data.pop("image", jpeg_bytes())
    return client.post(
        "/api/v1/vlm/query",
        data={"prompt": prompt, **data},
        files={"frame": ("snapshot.jpg", io.BytesIO(image), "image/jpeg")},
    )


def test_vlm_file_query_returns_typed_local_answer(client: TestClient) -> None:
    response = post_vlm(client)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload == {
        "schema_version": "1.0.0",
        "server_time": payload["server_time"],
        "model": "moondream2",
        "text": "A bus is visible in front of the camera.",
        "timings": payload["timings"],
    }
    assert all(value >= 0 for value in payload["timings"].values())


def test_vlm_accepts_base64_jpeg(client: TestClient) -> None:
    encoded = base64.b64encode(jpeg_bytes()).decode("ascii")
    response = client.post(
        "/api/v1/vlm/query",
        data={
            "prompt": "Describe this scene.",
            "image_base64": f"data:image/jpeg;base64,{encoded}",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["text"] == "A bus is visible in front of the camera."


def test_vlm_input_failures_use_stable_errors(client: TestClient) -> None:
    neither = client.post("/api/v1/vlm/query", data={"prompt": "Describe it."})
    assert neither.status_code == 422
    assert neither.json()["error"]["code"] == "INVALID_REQUEST"

    both = client.post(
        "/api/v1/vlm/query",
        data={
            "prompt": "Describe it.",
            "image_base64": base64.b64encode(jpeg_bytes()).decode("ascii"),
        },
        files={"frame": ("snapshot.jpg", io.BytesIO(jpeg_bytes()), "image/jpeg")},
    )
    assert both.status_code == 422
    assert both.json()["error"]["code"] == "INVALID_REQUEST"

    wrong_type = client.post(
        "/api/v1/vlm/query",
        data={"prompt": "Describe it."},
        files={"frame": ("snapshot.png", io.BytesIO(b"png"), "image/png")},
    )
    assert wrong_type.status_code == 415
    assert wrong_type.json()["error"]["code"] == "INVALID_CONTENT_TYPE"

    malformed = post_vlm(client, image=b"not-a-jpeg")
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "IMAGE_DECODE_FAILED"

    invalid_base64 = client.post(
        "/api/v1/vlm/query",
        data={"prompt": "Describe it.", "image_base64": "%%%"},
    )
    assert invalid_base64.status_code == 422
    assert invalid_base64.json()["error"]["code"] == "INVALID_REQUEST"

    blank_prompt = post_vlm(client, prompt="   ")
    assert blank_prompt.status_code == 422
    assert blank_prompt.json()["error"]["code"] == "INVALID_REQUEST"


def test_vlm_snapshot_is_never_persisted(client: TestClient, tmp_path: Path) -> None:
    assert post_vlm(client).status_code == 200
    created = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert created <= {"data/drishti.db", "logs/drishti.log"}


def test_unavailable_vlm_does_not_disable_walk_mode(settings: Settings) -> None:
    app = create_app(
        settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=ReadyTestOCR(),
        vlm_override=UnavailableVLMEngine("Local VLM missing."),
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client:
        failed = post_vlm(client)
        health = client.get("/api/v1/health")
        walk = client.post("/api/v1/walk/sessions", json={})

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "MODEL_NOT_READY"
    assert health.json()["models"]["vlm"]["status"] == "UNAVAILABLE"
    assert health.json()["walk_mode_available"] is True
    assert walk.status_code == 201


def test_active_vlm_rejects_queue_while_walk_remains_available(
    settings: Settings,
) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingVLM(ReadyTestVLM):
        def query(self, _image: np.ndarray, _prompt: str) -> VLMResult:
            started.set()
            release.wait(timeout=5)
            return VLMResult("A chair is ahead.", 1.0, 2.0, 0.5)

    app = create_app(
        settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=ReadyTestOCR(),
        vlm_override=BlockingVLM(),
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(post_vlm, client)
        assert started.wait(timeout=5)
        walk_session = client.post("/api/v1/walk/sessions", json={}).json()
        walk = client.post(
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
        busy = post_vlm(client)
        release.set()
        completed = first.result(timeout=5)

    assert walk.status_code == 200
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "CONFLICT"
    assert completed.status_code == 200
