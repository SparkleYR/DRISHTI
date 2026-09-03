from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import PROJECT_ROOT, Settings
from app.db.models import Base
from app.explore.local_vlm import load_vlm_engine
from app.main import create_app
from conftest import ReadyTestOCR


MODEL_PATH = PROJECT_ROOT / "models" / "vlm" / "moondream2"
TOKENIZER_PATH = PROJECT_ROOT / "models" / "vlm" / "starmie-v1" / "tokenizer.json"
FIXTURE_PATH = PROJECT_ROOT / "test-media" / "phase2" / "ultralytics-bus.jpg"


@pytest.mark.real_vlm
@pytest.mark.skipif(
    not (MODEL_PATH / "config.json").is_file()
    or not TOKENIZER_PATH.is_file()
    or not FIXTURE_PATH.is_file(),
    reason="Development-downloaded Moondream2 assets or bus fixture are absent.",
)
def test_real_moondream_runs_offline_and_releases_cuda_for_walk(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    settings = Settings(
        database_path=tmp_path / "drishti.db",
        evidence_dir=tmp_path / "evidence",
        log_file=tmp_path / "drishti.log",
        vlm_model_path=MODEL_PATH,
        vlm_tokenizer_path=TOKENIZER_PATH,
        compute_device="CUDA",
    )
    vlm = load_vlm_engine(settings)
    assert vlm.ready, vlm.detail
    locate_started = threading.Event()

    class SignallingVLM:
        @property
        def ready(self):
            return vlm.ready

        @property
        def detail(self):
            return vlm.detail

        def query(self, image, prompt):
            return vlm.query(image, prompt)

        def locate(self, image, target_name):
            locate_started.set()
            return vlm.locate(image, target_name)

        def unload(self):
            return vlm.unload()

    app = create_app(
        settings,
        ocr_override=ReadyTestOCR(),
        vlm_override=SignallingVLM(),
    )
    Base.metadata.create_all(app.state.database_engine)
    fixture = FIXTURE_PATH.read_bytes()
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        response = client.post(
            "/api/v1/vlm/query",
            data={"prompt": "What large vehicle is visible in this image?"},
            files={"frame": ("bus.jpg", io.BytesIO(fixture), "image/jpeg")},
        )
        walk_session = client.post("/api/v1/walk/sessions", json={}).json()
        before_locate = client.post(
            "/api/v1/walk/analyze",
            data={
                "session_id": walk_session["session_id"],
                "frame_id": "0",
                "captured_at": datetime.now(UTC).isoformat(),
                "rotation_degrees": "0",
            },
            files={
                "frame": ("walk.jpg", io.BytesIO(fixture), "image/jpeg")
            },
        )
        locate_future = pool.submit(
            client.post,
            "/api/v1/vlm/locate",
            params={
                "target_name": "bus",
                "session_id": walk_session["session_id"],
            },
        )
        assert locate_started.wait(timeout=5)
        during_locate = client.post(
            "/api/v1/walk/analyze",
            data={
                "session_id": walk_session["session_id"],
                "frame_id": "1",
                "captured_at": datetime.now(UTC).isoformat(),
                "rotation_degrees": "0",
            },
            files={
                "frame": ("walk.jpg", io.BytesIO(fixture), "image/jpeg")
            },
        )
        locate = locate_future.result(timeout=60)
        health = client.get("/api/v1/health")
        walk = client.post(
            "/api/v1/walk/analyze",
            data={
                "session_id": walk_session["session_id"],
                "frame_id": "2",
                "captured_at": datetime.now(UTC).isoformat(),
                "rotation_degrees": "0",
            },
            files={
                "frame": ("walk.jpg", io.BytesIO(fixture), "image/jpeg")
            },
        )

    assert response.status_code == 200, response.text
    assert "bus" in response.json()["text"].lower()
    assert response.json()["timings"]["load_ms"] > 0
    assert response.json()["timings"]["inference_ms"] > 0
    assert response.json()["timings"]["unload_ms"] >= 0
    assert before_locate.status_code == 200, before_locate.text
    assert during_locate.status_code == 200, during_locate.text
    assert during_locate.json()["target_tracking"]["tracking_state"] == "LOCATING"
    assert locate.status_code == 200, locate.text
    assert locate.json()["target"]["box"]
    assert locate.json()["tracking_allowed"] is True
    assert locate.json()["source_frame_id"] == 0
    assert locate.json()["timings"]["unload_ms"] >= 0
    assert health.json()["models"]["vlm"]["status"] == "READY"
    assert health.json()["walk_mode_available"] is True
    assert walk.status_code == 200, walk.text
    assert walk.json()["detections"]
    assert walk.json()["target_tracking"]["tracking_state"] in {
        "LOCKED_TRACKING",
        "TARGET_LOST",
    }
