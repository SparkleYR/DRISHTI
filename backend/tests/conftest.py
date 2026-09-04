from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.db.models import Base
from app.main import create_app
from app.explore.ocr import OCRResult
from app.explore.local_vlm import VLMLocationResult, VLMResult
from app.perception.detector import DetectionCandidate, DetectionSet
from app.perception.segmenter import SegmentationFrame


class ReadyTestDetector:
    def __init__(
        self,
        detections: list[DetectionCandidate] | None = None,
        all_detections: list[DetectionCandidate] | None = None,
    ) -> None:
        self.detections = detections or []
        # Defaults to the risk list so tests that only set `detections` keep
        # exercising both filterings with the same boxes (D-078).
        self.all_detections = all_detections
        self.call_count = 0

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return "Test detector ready."

    def detect(self, _image) -> DetectionSet:
        self.call_count += 1
        full = self.detections if self.all_detections is None else self.all_detections
        return DetectionSet(risk=list(self.detections), all=list(full))


class ReadyTestSegmenter:
    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return "Test segmenter ready."

    def segment(self, image: np.ndarray) -> SegmentationFrame:
        height, width = image.shape[:2]
        return SegmentationFrame(
            class_map=np.full((height, width), 10, dtype=np.uint8),
            confidence_map=np.full((height, width), 0.8, dtype=np.float32),
            id_to_label={10: "sky"},
        )


class ReadyTestOCR:
    def __init__(self, result: OCRResult | None = None) -> None:
        self.result = result or OCRResult("BUS 42A CENTRAL STATION", 0.92)
        self.call_count = 0

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return "Test Tesseract ready on CPU."

    def read_text(self, _image: np.ndarray) -> OCRResult:
        self.call_count += 1
        return self.result


class ReadyTestVLM:
    def __init__(self, text: str = "A bus is visible in front of the camera.") -> None:
        self.text = text
        self.call_count = 0
        self.unload_count = 0

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return "Test local VLM ready for on-demand use."

    def query(self, _image: np.ndarray, _prompt: str) -> VLMResult:
        self.call_count += 1
        return VLMResult(
            text=self.text,
            load_ms=1.0,
            inference_ms=2.0,
            unload_ms=0.5,
        )

    def locate(self, _image: np.ndarray, _target_name: str) -> VLMLocationResult:
        self.call_count += 1
        return VLMLocationResult(
            box=(0.20, 0.30, 0.50, 0.80),
            point=(0.35, 0.55),
            confidence=None,
            load_ms=1.0,
            inference_ms=2.0,
            unload_ms=0.5,
        )

    def unload(self) -> None:
        self.unload_count += 1


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "data" / "drishti.db",
        evidence_dir=tmp_path / "data" / "evidence",
        log_file=tmp_path / "logs" / "drishti.log",
        compute_device="CUDA",
        compute_device_name="Test CUDA device",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(
        settings,
        detector_override=ReadyTestDetector(),
        segmenter_override=ReadyTestSegmenter(),
        ocr_override=ReadyTestOCR(),
        vlm_override=ReadyTestVLM(),
    )
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as test_client:
        yield test_client
