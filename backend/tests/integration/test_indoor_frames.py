from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.perception.detector import load_detector
from app.perception.segmenter import load_segmenter


FIXTURE_ENV = "DRISHTI_INDOOR_FIXTURE_DIR"


@pytest.mark.real_indoor
def test_approved_indoor_frame_regressions(tmp_path: Path) -> None:
    fixture_value = os.environ.get(FIXTURE_ENV)
    if not fixture_value:
        pytest.skip(
            f"Set {FIXTURE_ENV} to an approved external controlled-fixture directory."
        )
    fixture_dir = Path(fixture_value).resolve()
    manifest_path = fixture_dir / "expectations.json"
    if not manifest_path.is_file():
        pytest.fail(f"Missing indoor fixture manifest: {manifest_path}")
    cases = json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]
    if len(cases) < 5:
        pytest.fail("Indoor regression manifest must cover at least five controlled scenes.")

    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "drishti.db",
        log_file=tmp_path / "drishti.log",
        models_dir=PROJECT_ROOT / "models",
        detector_model_path=PROJECT_ROOT / "models" / "detector" / "yolo11n.pt",
        segmentation_model_path=(
            PROJECT_ROOT / "models" / "segmentation" / "segformer-b0-ade20k"
        ),
        segmentation_label_set="ADE20K",
        compute_device="CUDA",
    )
    detector = load_detector(settings)
    segmenter = load_segmenter(settings)
    assert detector.ready, detector.detail
    assert segmenter.ready, segmenter.detail

    app = create_app(
        settings,
        detector_override=detector,
        segmenter_override=segmenter,
    )
    timings: list[float] = []
    with TestClient(app) as client:
        for case in cases:
            image_path = (fixture_dir / case["file"]).resolve()
            assert image_path.parent == fixture_dir
            assert image_path.is_file(), image_path
            session = client.post("/api/v1/walk/sessions", json={}).json()
            result = None
            for frame_id in range(settings.alert_persistence_frames):
                with image_path.open("rb") as image:
                    response = client.post(
                        "/api/v1/walk/analyze",
                        data={
                            "session_id": session["session_id"],
                            "frame_id": str(frame_id),
                            "captured_at": datetime.now(UTC).isoformat(),
                            "rotation_degrees": "0",
                        },
                        files={"frame": (image_path.name, image, "image/jpeg")},
                    )
                assert response.status_code == 200, response.text
                result = response.json()
                timings.append(result["timings"]["total_ms"])
            assert result is not None
            assert result["guidance"]["action"] in case["allowed_actions"]
            assert result["guidance"]["action"] not in case.get(
                "forbidden_actions", []
            )
            if expected_reason := case.get("reason_code"):
                assert result["guidance"]["reason_code"] == expected_reason
            assert len(result["overlay"]["safe_polygons"]) >= case.get(
                "minimum_safe_polygons", 0
            )

    timings.sort()
    p95 = timings[min(len(timings) - 1, int(len(timings) * 0.95))]
    assert p95 <= 250.0, f"Indoor replay p95 {p95:.1f} ms exceeds 250 ms."
