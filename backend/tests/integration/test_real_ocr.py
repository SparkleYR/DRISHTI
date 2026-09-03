from __future__ import annotations

import io
from pathlib import Path

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.config import PROJECT_ROOT, Settings
from app.db.models import Base
from app.explore.ocr import load_ocr_reader
from app.main import create_app
from conftest import ReadyTestDetector, ReadyTestSegmenter


TESSERACT_PATH = PROJECT_ROOT / ".tools" / "Tesseract-OCR" / "tesseract.exe"


def prepared_sign_jpeg() -> bytes:
    image = np.full((360, 1280, 3), 255, dtype=np.uint8)
    cv2.putText(
        image,
        "BUS 42A CENTRAL",
        (55, 225),
        cv2.FONT_HERSHEY_SIMPLEX,
        3.0,
        (0, 0, 0),
        8,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return encoded.tobytes()


@pytest.mark.real_ocr
@pytest.mark.skipif(
    not TESSERACT_PATH.is_file(),
    reason="The approved local Tesseract 5 runtime is not present.",
)
def test_real_tesseract_runs_offline_through_explore_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def deny_outbound_http(*_args, **_kwargs):
        raise AssertionError("Runtime OCR attempted outbound HTTP.")

    monkeypatch.setattr("requests.sessions.Session.request", deny_outbound_http)
    settings = Settings(
        database_path=tmp_path / "drishti.db",
        evidence_dir=tmp_path / "evidence",
        log_file=tmp_path / "drishti.log",
        tesseract_command=str(TESSERACT_PATH),
    )
    reader = load_ocr_reader(settings)
    assert reader.ready, reader.detail
    assert "CPU" in reader.detail

    app = create_app(
        settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=reader,
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/explore",
            data={"mode": "READ_TEXT", "preferred_language": "en"},
            files={
                "frame": (
                    "prepared-sign.jpg",
                    io.BytesIO(prepared_sign_jpeg()),
                    "image/jpeg",
                )
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["no_text_found"] is False
    assert "BUS" in payload["text"].upper()
    assert "42A" in payload["route_numbers"]
    assert payload["confidence_qualification"] in {"HIGH", "LOW"}
    assert payload["timings"]["ocr_ms"] >= 0
    assert not (tmp_path / "evidence").exists()
