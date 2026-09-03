from __future__ import annotations

import base64
import binascii
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.explore.local_vlm import VLMEngine, VLMError, VLMResourceError
from app.explore.vlm_executor import VLMExecutor
from app.frame_ingress import JPEG_CONTENT_TYPE, decode_jpeg
from app.schemas.common import utc_now
from app.schemas.vlm import VLMTimings, VLMQueryResponse
from app.schemas.walk import RotationDegrees


router = APIRouter(prefix="/api/v1/vlm", tags=["vlm"])


@router.post("/query", response_model=VLMQueryResponse)
async def query_vlm(
    request: Request,
    prompt: Annotated[str, Form(min_length=1, max_length=500)],
    frame: Annotated[UploadFile | None, File()] = None,
    image_base64: Annotated[str | None, Form()] = None,
) -> VLMQueryResponse:
    started = perf_counter()
    prompt = prompt.strip()
    if not prompt:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "The VLM prompt must contain non-whitespace text.",
            status_code=422,
        )

    settings: Settings = request.app.state.settings
    engine: VLMEngine = request.app.state.vlm_engine
    if not engine.ready:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM is unavailable.",
            status_code=503,
            retryable=True,
            details={"vlm": engine.detail},
        )

    frame_bytes = await _read_image_payload(
        frame,
        image_base64,
        max_bytes=settings.vlm_max_image_bytes,
    )
    decode_started = perf_counter()
    decoded = await run_in_threadpool(
        decode_jpeg,
        frame_bytes,
        rotation_degrees=RotationDegrees.DEG_0,
        max_image_width=settings.vlm_max_image_width,
        max_image_pixels=settings.vlm_max_image_pixels,
    )
    decode_ms = (perf_counter() - decode_started) * 1000
    del frame_bytes

    executor: VLMExecutor = request.app.state.vlm_executor
    try:
        result = await executor.run(
            lambda: engine.query(decoded.image, prompt),
            timeout_seconds=settings.vlm_timeout_seconds,
        )
    except AppError:
        raise
    except VLMResourceError as exc:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM could not reserve safe CUDA memory.",
            status_code=503,
            retryable=True,
            details={"reason": str(exc)},
        ) from exc
    except VLMError as exc:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM could not process this snapshot.",
            status_code=503,
            retryable=True,
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM could not process this snapshot.",
            status_code=503,
            retryable=True,
            details={"reason": type(exc).__name__},
        ) from exc

    total_ms = (perf_counter() - started) * 1000
    return VLMQueryResponse(
        server_time=utc_now(),
        text=result.text,
        timings=VLMTimings(
            decode_ms=decode_ms,
            load_ms=result.load_ms,
            inference_ms=result.inference_ms,
            unload_ms=result.unload_ms,
            total_ms=total_ms,
        ),
    )


async def _read_image_payload(
    frame: UploadFile | None,
    image_base64: str | None,
    *,
    max_bytes: int,
) -> bytes:
    if (frame is None) == (image_base64 is None):
        if frame is not None:
            await frame.close()
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "Provide exactly one of frame or image_base64.",
            status_code=422,
        )

    if frame is not None:
        if frame.content_type != JPEG_CONTENT_TYPE:
            await frame.close()
            raise AppError(
                ErrorCode.INVALID_CONTENT_TYPE,
                "The VLM snapshot must use image/jpeg.",
                status_code=415,
            )
        if getattr(frame.file, "_rolled", False):
            await frame.close()
            raise AppError(
                ErrorCode.IMAGE_TOO_LARGE,
                "The VLM image exceeded the local in-memory boundary.",
                status_code=413,
            )
        payload = await frame.read(max_bytes + 1)
        await frame.close()
    else:
        assert image_base64 is not None
        encoded = image_base64.strip()
        prefix = "data:image/jpeg;base64,"
        if encoded.lower().startswith(prefix):
            encoded = encoded[len(prefix) :]
        if len(encoded) > ((max_bytes + 2) // 3) * 4 + 4:
            raise _too_large(max_bytes)
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "image_base64 is not valid base64-encoded JPEG data.",
                status_code=422,
            ) from exc

    if len(payload) > max_bytes:
        raise _too_large(max_bytes)
    return payload


def _too_large(max_bytes: int) -> AppError:
    return AppError(
        ErrorCode.IMAGE_TOO_LARGE,
        "The VLM snapshot exceeds the local byte limit.",
        status_code=413,
        details={"vlm_max_image_bytes": max_bytes},
    )
