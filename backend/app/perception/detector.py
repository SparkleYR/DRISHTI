from __future__ import annotations

from dataclasses import dataclass
import logging
from math import isfinite
import os
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, runtime_checkable

import numpy as np

from app.config import Settings


logger = logging.getLogger(__name__)

CANONICAL_LABELS = frozenset(
    {
        "person",
        "chair",
        "bag",
        "desk",
        "bicycle",
        "motorcycle",
        "car",
        "bus",
        "bench",
    }
)
LABEL_ALIASES = {
    "backpack": "bag",
    "handbag": "bag",
    "dining table": "desk",
    "table": "desk",
}


@dataclass(frozen=True)
class RawDetection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class DetectionCandidate:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


@runtime_checkable
class Detector(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def detail(self) -> str: ...

    def detect(self, image: np.ndarray) -> list[DetectionCandidate]: ...


class UnavailableDetector:
    def __init__(self, detail: str) -> None:
        self._detail = detail

    @property
    def ready(self) -> bool:
        return False

    @property
    def detail(self) -> str:
        return self._detail

    def detect(self, image: np.ndarray) -> list[DetectionCandidate]:
        del image
        raise RuntimeError(self._detail)


class UltralyticsDetector:
    def __init__(
        self,
        model: Any,
        *,
        device: str | int,
        device_name: str,
        confidence_threshold: float,
        image_size: int,
    ) -> None:
        self._model = model
        self._device = device
        self._device_name = device_name
        self._confidence_threshold = confidence_threshold
        self._image_size = image_size
        self._lock = Lock()

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return f"YOLO11n ready on {self._device_name}."

    def detect(self, image: np.ndarray) -> list[DetectionCandidate]:
        with self._lock:
            results = self._model.predict(
                source=image,
                conf=self._confidence_threshold,
                imgsz=self._image_size,
                device=self._device,
                verbose=False,
            )
        if not results:
            return []

        result = results[0]
        boxes = result.boxes
        if boxes is None:
            return []
        names = result.names
        raw = [
            RawDetection(
                label=str(names[int(class_id)]),
                confidence=float(confidence),
                x1=float(coordinates[0]),
                y1=float(coordinates[1]),
                x2=float(coordinates[2]),
                y2=float(coordinates[3]),
            )
            for coordinates, confidence, class_id in zip(
                boxes.xyxy.detach().cpu().tolist(),
                boxes.conf.detach().cpu().tolist(),
                boxes.cls.detach().cpu().tolist(),
                strict=True,
            )
        ]
        height, width = image.shape[:2]
        return canonicalize_detections(
            raw,
            width=width,
            height=height,
            confidence_threshold=self._confidence_threshold,
        )


def canonicalize_detections(
    detections: list[RawDetection],
    *,
    width: int,
    height: int,
    confidence_threshold: float,
) -> list[DetectionCandidate]:
    if width <= 0 or height <= 0:
        raise ValueError("Detection image dimensions must be positive.")

    canonical: list[DetectionCandidate] = []
    for item in detections:
        if not all(
            isfinite(value)
            for value in (
                item.confidence,
                item.x1,
                item.y1,
                item.x2,
                item.y2,
            )
        ):
            continue
        label = LABEL_ALIASES.get(item.label.lower(), item.label.lower())
        if label not in CANONICAL_LABELS or item.confidence < confidence_threshold:
            continue
        x1 = _clamp(item.x1 / width)
        y1 = _clamp(item.y1 / height)
        x2 = _clamp(item.x2 / width)
        y2 = _clamp(item.y2 / height)
        if x1 >= x2 or y1 >= y2:
            continue
        canonical.append(
            DetectionCandidate(
                label=label,
                confidence=_clamp(item.confidence),
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
            )
        )
    return canonical


def load_detector(settings: Settings) -> Detector:
    model_path = settings.detector_model_path.resolve()
    models_dir = settings.models_dir.resolve()
    try:
        model_path.relative_to(models_dir)
    except ValueError:
        return UnavailableDetector("Detector path must remain inside the local models directory.")

    if not model_path.is_file():
        return UnavailableDetector(f"Local YOLO11n weights are missing at {model_path}.")
    if settings.compute_device == "NONE":
        return UnavailableDetector("No inference device is configured.")

    ultralytics_config_dir = settings.database_path.parent / "ultralytics"
    matplotlib_config_dir = settings.database_path.parent / "matplotlib"
    ultralytics_config_dir.mkdir(parents=True, exist_ok=True)
    matplotlib_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["YOLO_OFFLINE"] = "True"
    os.environ["YOLO_AUTOINSTALL"] = "False"
    os.environ["YOLO_CONFIG_DIR"] = str(ultralytics_config_dir.resolve())
    os.environ["MPLCONFIGDIR"] = str(matplotlib_config_dir.resolve())

    try:
        import torch
        from ultralytics import YOLO

        if settings.compute_device == "CUDA":
            if not torch.cuda.is_available():
                return UnavailableDetector("CUDA was selected but PyTorch cannot access the GPU.")
            device: str | int = 0
            device_name = torch.cuda.get_device_name(0)
        else:
            device = "cpu"
            device_name = "CPU"

        model = YOLO(str(model_path), task="detect")
        detector = UltralyticsDetector(
            model,
            device=device,
            device_name=device_name,
            confidence_threshold=settings.detector_confidence_threshold,
            image_size=settings.detector_image_size,
        )
        detector.detect(
            np.zeros(
                (settings.detector_image_size, settings.detector_image_size, 3),
                dtype=np.uint8,
            )
        )
        return detector
    except Exception as exc:
        logger.exception("Local YOLO11n detector failed to initialize")
        return UnavailableDetector(f"Local YOLO11n initialization failed: {type(exc).__name__}.")


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
