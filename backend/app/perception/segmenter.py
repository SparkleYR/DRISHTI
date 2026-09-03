from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from threading import Lock
from typing import Any, Protocol

import cv2
import numpy as np

from app.config import Settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SegmentationFrame:
    class_map: np.ndarray
    confidence_map: np.ndarray
    id_to_label: dict[int, str]


class Segmenter(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def detail(self) -> str: ...

    def segment(self, image: np.ndarray) -> SegmentationFrame: ...


class UnavailableSegmenter:
    def __init__(self, detail: str) -> None:
        self._detail = detail

    @property
    def ready(self) -> bool:
        return False

    @property
    def detail(self) -> str:
        return self._detail

    def segment(self, image: np.ndarray) -> SegmentationFrame:
        del image
        raise RuntimeError(self._detail)


class SegFormerSegmenter:
    def __init__(
        self,
        *,
        processor: Any,
        model: Any,
        torch_module: Any,
        device: Any,
        device_name: str,
        input_height: int,
        input_width: int,
    ) -> None:
        self._processor = processor
        self._model = model
        self._torch = torch_module
        self._device = device
        self._device_name = device_name
        self._input_height = input_height
        self._input_width = input_width
        self._lock = Lock()
        self._id_to_label = {
            int(class_id): str(label).lower()
            for class_id, label in model.config.id2label.items()
        }

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return f"SegFormer-B0 Cityscapes ready on {self._device_name}."

    def segment(self, image: np.ndarray) -> SegmentationFrame:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        with self._lock:
            inputs = self._processor(
                images=rgb,
                return_tensors="pt",
                size={"height": self._input_height, "width": self._input_width},
            )
            pixel_values = inputs["pixel_values"].to(self._device)
            with self._torch.inference_mode():
                logits = self._model(pixel_values=pixel_values).logits
                probabilities = self._torch.softmax(logits, dim=1)
                confidence, classes = probabilities.max(dim=1)

        source_height, source_width = image.shape[:2]
        class_map = cv2.resize(
            classes[0].detach().cpu().numpy().astype(np.uint8),
            (source_width, source_height),
            interpolation=cv2.INTER_NEAREST,
        )
        confidence_map = cv2.resize(
            confidence[0].detach().cpu().numpy().astype(np.float32),
            (source_width, source_height),
            interpolation=cv2.INTER_LINEAR,
        )
        return SegmentationFrame(
            class_map=class_map,
            confidence_map=np.clip(confidence_map, 0.0, 1.0),
            id_to_label=self._id_to_label,
        )


def load_segmenter(settings: Settings) -> Segmenter:
    model_path = settings.segmentation_model_path.resolve()
    models_dir = settings.models_dir.resolve()
    try:
        model_path.relative_to(models_dir)
    except ValueError:
        return UnavailableSegmenter(
            "Segmentation path must remain inside the local models directory."
        )

    required_files = {
        "config.json",
        "preprocessor_config.json",
        "pytorch_model.bin",
    }
    if not model_path.is_dir() or not all(
        (model_path / filename).is_file() for filename in required_files
    ):
        return UnavailableSegmenter(
            f"Local SegFormer-B0 files are incomplete at {model_path}."
        )
    if settings.compute_device == "NONE":
        return UnavailableSegmenter("No segmentation inference device is configured.")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    try:
        import torch
        from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

        if settings.compute_device == "CUDA":
            if not torch.cuda.is_available():
                return UnavailableSegmenter(
                    "CUDA was selected but PyTorch cannot access the GPU."
                )
            device = torch.device("cuda:0")
            device_name = torch.cuda.get_device_name(0)
        else:
            device = torch.device("cpu")
            device_name = "CPU"

        processor = AutoImageProcessor.from_pretrained(
            model_path,
            local_files_only=True,
            use_fast=False,
        )
        model = SegformerForSemanticSegmentation.from_pretrained(
            model_path,
            local_files_only=True,
        )
        model.to(device)
        model.eval()
        segmenter = SegFormerSegmenter(
            processor=processor,
            model=model,
            torch_module=torch,
            device=device,
            device_name=device_name,
            input_height=settings.segmentation_input_height,
            input_width=settings.segmentation_input_width,
        )
        segmenter.segment(
            np.zeros(
                (
                    settings.segmentation_input_height,
                    settings.segmentation_input_width,
                    3,
                ),
                dtype=np.uint8,
            )
        )
        return segmenter
    except Exception as exc:
        logger.exception("Local SegFormer-B0 segmenter failed to initialize")
        return UnavailableSegmenter(
            f"Local SegFormer-B0 initialization failed: {type(exc).__name__}."
        )
