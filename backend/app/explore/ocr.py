from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from app.config import Settings

try:
    import pytesseract
    from pytesseract import Output
except ImportError:  # pragma: no cover - exercised only in incomplete environments
    pytesseract = None
    Output = None


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class OCRReader(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def detail(self) -> str: ...

    def read_text(self, image: np.ndarray) -> OCRResult: ...


class UnavailableOCRReader:
    def __init__(self, detail: str) -> None:
        self._detail = detail

    @property
    def ready(self) -> bool:
        return False

    @property
    def detail(self) -> str:
        return self._detail

    def read_text(self, _image: np.ndarray) -> OCRResult:
        raise RuntimeError(self._detail)


class TesseractOCRReader:
    def __init__(self, command: str, language: str, version: str) -> None:
        self._language = language
        self._version = version
        assert pytesseract is not None
        pytesseract.pytesseract.tesseract_cmd = command

    @property
    def ready(self) -> bool:
        return True

    @property
    def detail(self) -> str:
        return f"Tesseract {self._version} ready on CPU ({self._language})."

    def read_text(self, image: np.ndarray) -> OCRResult:
        assert pytesseract is not None and Output is not None
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        normalized = cv2.normalize(grayscale, None, 0, 255, cv2.NORM_MINMAX)
        data = pytesseract.image_to_data(
            normalized,
            lang=self._language,
            config="--oem 3 --psm 6",
            output_type=Output.DICT,
        )
        words: list[str] = []
        confidences: list[tuple[float, int]] = []
        for raw_text, raw_confidence in zip(data["text"], data["conf"]):
            text = " ".join(str(raw_text).strip().split())
            if not text:
                continue
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                continue
            if confidence < 0:
                continue
            words.append(text)
            confidences.append((min(confidence, 100.0) / 100.0, len(text)))
        if not words or not confidences:
            return OCRResult(text="", confidence=0.0)
        total_weight = sum(weight for _confidence, weight in confidences)
        weighted_confidence = sum(
            confidence * weight for confidence, weight in confidences
        ) / max(1, total_weight)
        return OCRResult(text=" ".join(words), confidence=weighted_confidence)


def load_ocr_reader(settings: Settings) -> OCRReader:
    if pytesseract is None:
        return UnavailableOCRReader("pytesseract is not installed.")
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    try:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_command
        version = str(pytesseract.get_tesseract_version()).splitlines()[0]
        languages = set(pytesseract.get_languages(config=""))
    except Exception as exc:
        return UnavailableOCRReader(
            f"The local Tesseract executable is unavailable ({type(exc).__name__})."
        )
    if settings.ocr_language not in languages:
        return UnavailableOCRReader(
            f"Tesseract language data '{settings.ocr_language}' is unavailable."
        )
    return TesseractOCRReader(
        settings.tesseract_command,
        settings.ocr_language,
        version,
    )


ROUTE_TOKEN = re.compile(r"(?<![A-Z0-9])[A-Z]{0,2}\d{1,4}[A-Z]?(?![A-Z0-9])", re.I)


def extract_route_numbers(text: str) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for match in ROUTE_TOKEN.finditer(text.upper()):
        value = match.group(0)
        if value not in seen:
            seen.add(value)
            results.append(value)
    return results
