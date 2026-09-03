from __future__ import annotations

from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.explore.executor import ExploreExecutor
from app.explore.ocr import OCRReader, OCRResult, extract_route_numbers
from app.frame_ingress import JPEG_CONTENT_TYPE, decode_jpeg
from app.schemas.common import utc_now
from app.schemas.explore import (
    ExploreMode,
    ExploreTimings,
    OcrConfidenceQualification,
    ReadTextResponse,
)
from app.schemas.walk import RotationDegrees


router = APIRouter(prefix="/api/v1/explore", tags=["explore"])


@router.post("", response_model=ReadTextResponse)
async def read_text(
    request: Request,
    frame: Annotated[UploadFile, File()],
    mode: Annotated[ExploreMode, Form()],
    preferred_language: Annotated[str, Form(min_length=2, max_length=35)] = "en",
) -> ReadTextResponse:
    started = perf_counter()
    settings: Settings = request.app.state.settings
    reader: OCRReader = request.app.state.ocr_reader
    if not reader.ready:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local OCR runtime is unavailable.",
            status_code=503,
            retryable=True,
            details={"ocr": reader.detail},
        )
    _require_english(preferred_language)
    if frame.content_type != JPEG_CONTENT_TYPE:
        raise AppError(
            ErrorCode.INVALID_CONTENT_TYPE,
            "The Explore frame must use image/jpeg.",
            status_code=415,
        )
    if getattr(frame.file, "_rolled", False):
        raise AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            "The Explore image exceeded the local in-memory boundary.",
            status_code=413,
        )
    frame_bytes = await frame.read(settings.explore_max_image_bytes + 1)
    await frame.close()
    if len(frame_bytes) > settings.explore_max_image_bytes:
        raise AppError(
            ErrorCode.IMAGE_TOO_LARGE,
            "The Explore JPEG exceeds the local byte limit.",
            status_code=413,
            details={"explore_max_image_bytes": settings.explore_max_image_bytes},
        )

    decode_started = perf_counter()
    decoded = await run_in_threadpool(
        decode_jpeg,
        frame_bytes,
        rotation_degrees=RotationDegrees.DEG_0,
        max_image_width=settings.explore_max_image_width,
        max_image_pixels=settings.explore_max_image_pixels,
    )
    decode_ms = (perf_counter() - decode_started) * 1000
    del frame_bytes

    executor: ExploreExecutor = request.app.state.explore_executor
    ocr_started = perf_counter()
    try:
        result = await executor.run(lambda: reader.read_text(decoded.image))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local OCR worker could not read this image.",
            status_code=503,
            retryable=True,
            details={"reason": type(exc).__name__},
        ) from exc
    ocr_ms = (perf_counter() - ocr_started) * 1000
    return _build_response(
        result,
        threshold=settings.ocr_confidence_threshold,
        decode_ms=decode_ms,
        ocr_ms=ocr_ms,
        total_ms=(perf_counter() - started) * 1000,
    )


def _require_english(language: str) -> None:
    normalized = language.strip().lower().replace("_", "-")
    if normalized != "en" and not normalized.startswith("en-"):
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "Phase 7 supports English OCR only.",
            status_code=422,
            details={"preferred_language": language},
        )


def _build_response(
    result: OCRResult,
    *,
    threshold: float,
    decode_ms: float,
    ocr_ms: float,
    total_ms: float,
) -> ReadTextResponse:
    text = " ".join(result.text.strip().split())
    confidence = max(0.0, min(1.0, result.confidence))
    if not text:
        qualification = OcrConfidenceQualification.NONE
        confidence = 0.0
        message = "No text found."
    elif confidence < threshold:
        qualification = OcrConfidenceQualification.LOW
        message = f"Possible text: {text}"
    else:
        qualification = OcrConfidenceQualification.HIGH
        message = text
    return ReadTextResponse(
        server_time=utc_now(),
        text=text,
        route_numbers=extract_route_numbers(text),
        confidence=confidence,
        confidence_qualification=qualification,
        message=message,
        no_text_found=not text,
        timings=ExploreTimings(
            decode_ms=decode_ms,
            ocr_ms=ocr_ms,
            total_ms=total_ms,
        ),
    )
