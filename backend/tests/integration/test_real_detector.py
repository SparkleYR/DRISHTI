from pathlib import Path
from datetime import UTC, datetime
import os

import cv2
from fastapi.testclient import TestClient
import pytest

from app.config import PROJECT_ROOT, Settings
from app.db.models import Base
from app.main import create_app
from app.perception.detector import load_detector
from app.perception.segmenter import load_segmenter
from app.schemas.walk import SurfaceKind


MODEL_PATH = PROJECT_ROOT / "models" / "detector" / "yolo11n.pt"
FIXTURE_PATH = PROJECT_ROOT / "test-media" / "phase2" / "ultralytics-bus.jpg"
SEGMENTATION_PATH = (
    PROJECT_ROOT / "models" / "segmentation" / "segformer-b0-ade20k"
)


@pytest.mark.real_model
@pytest.mark.skipif(
    not MODEL_PATH.is_file()
    or not FIXTURE_PATH.is_file()
    or not SEGMENTATION_PATH.is_dir(),
    reason="Development-downloaded Phase 2/3 model assets are not present.",
)
def test_real_cuda_models_run_offline_through_api(
    tmp_path: Path, monkeypatch
) -> None:
    def deny_outbound_http(*_args, **_kwargs):
        raise AssertionError("Runtime detector startup attempted outbound HTTP.")

    monkeypatch.setattr("requests.sessions.Session.request", deny_outbound_http)
    settings = Settings(
        database_path=tmp_path / "drishti.db",
        log_file=tmp_path / "drishti.log",
        models_dir=PROJECT_ROOT / "models",
        detector_model_path=MODEL_PATH,
        segmentation_model_path=SEGMENTATION_PATH,
        segmentation_label_set="ADE20K",
        compute_device="CUDA",
    )
    detector = load_detector(settings)
    segmenter = load_segmenter(settings)
    image = cv2.imread(str(FIXTURE_PATH))

    assert detector.ready, detector.detail
    assert segmenter.ready, segmenter.detail
    assert "ADE20K" in segmenter.detail
    assert os.environ["YOLO_OFFLINE"] == "True"
    assert image is not None
    detections = detector.detect(image)
    labels = {detection.label for detection in detections}
    assert {"person", "bus"} <= labels
    assert all(0 <= value <= 1 for item in detections for value in (item.x1, item.y1, item.x2, item.y2))
    assert all(item.x1 < item.x2 and item.y1 < item.y2 for item in detections)

    app = create_app(
        settings,
        detector_override=detector,
        segmenter_override=segmenter,
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client:
        session = client.post("/api/v1/walk/sessions", json={}).json()
        responses = []
        for frame_id in range(5):
            with FIXTURE_PATH.open("rb") as fixture:
                responses.append(
                    client.post(
                        "/api/v1/walk/analyze",
                        data={
                            "session_id": session["session_id"],
                            "frame_id": str(frame_id),
                            "captured_at": datetime.now(UTC).isoformat(),
                            "rotation_degrees": "0",
                        },
                        files={"frame": ("bus.jpg", fixture, "image/jpeg")},
                    )
                )

    assert all(response.status_code == 200 for response in responses)
    payload = responses[-1].json()
    assert {item["label"] for item in payload["detections"]} >= {"person", "bus"}
    assert {item["kind"] for item in payload["surfaces"]} >= {
        SurfaceKind.WALKABLE,
        SurfaceKind.ROAD,
    }
    assert payload["timings"]["detection_ms"] >= 0
    assert payload["timings"]["segmentation_ms"] >= 0
    timings = sorted(response.json()["timings"]["total_ms"] for response in responses)
    assert timings[-1] <= 250.0
    assert "detector" not in payload["degraded_modules"]
