from __future__ import annotations

import base64
import binascii
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.explore.local_vlm import (
    VLMEngine,
    VLMError,
    VLMResourceError,
    VLMTargetNotFoundError,
)
from app.explore.vlm_executor import VLMExecutor
from app.frame_ingress import JPEG_CONTENT_TYPE, decode_jpeg
from app.schemas.common import utc_now
from app.guidance.target_guidance import (
    TargetGuidanceSessionStore,
    compatibility_clock_direction,
    guidance_text,
    range_hint,
)
from app.perception.landmark_memory import LandmarkMemoryStore, normalize_label
from app.scheduling.frame_memory import LatestFrameMemory
from app.schemas.vlm import (
    VLMLocatedTarget,
    VLMLocateResponse,
    VLMQueryResponse,
    VLMTargetBox,
    VLMTimings,
)
from app.schemas.walk import RotationDegrees


router = APIRouter(prefix="/api/v1/vlm", tags=["vlm"])


@router.post("/locate", response_model=VLMLocateResponse)
async def locate_vlm_target(
    request: Request,
    target_name: Annotated[str, Query(min_length=1, max_length=120)],
    session_id: Annotated[str | None, Query(min_length=1)] = None,
    frame: Annotated[UploadFile | None, File()] = None,
    image_base64: Annotated[str | None, Form()] = None,
) -> VLMLocateResponse:
    started = perf_counter()
    now = utc_now()
    now_ms = int(now.timestamp() * 1000)
    target_name = " ".join(target_name.strip().split())
    if not target_name:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "target_name must contain non-whitespace text.",
            status_code=422,
        )

    if session_id is not None:
        request.app.state.walk_sessions.require_active(session_id)
    target_sessions: TargetGuidanceSessionStore = (
        request.app.state.target_tracking_sessions
    )
    settings: Settings = request.app.state.settings
    # `remember()` writes straight past the person filter that `observe()`
    # applies, so refuse the request outright rather than seeding a landmark
    # and guiding a user toward a specific person (D-073 §4, D-078).
    if normalize_label(target_name) == "person" and not settings.landmark_allow_person:
        raise AppError(
            ErrorCode.NOT_FOUND,
            "I can't guide you to a person.",
            status_code=404,
        )
    landmark_memories: LandmarkMemoryStore = request.app.state.landmark_memories
    if session_id is not None:
        remembered = landmark_memories.resolve(
            session_id,
            target_name,
            now_ms=now_ms,
        )
        if remembered is not None:
            if frame is not None:
                await frame.close()
            frame_memory: LatestFrameMemory = request.app.state.latest_frame_memory
            snapshot = frame_memory.snapshot(session_id)
            visible = now_ms - remembered.last_seen_ms <= 2_000
            seed = target_sessions.start_guidance(
                session_id,
                target_name=target_name,
                landmark=remembered,
                now_ms=now_ms,
                heading_degrees=snapshot.heading_degrees,
                visible=visible,
            )
            box = remembered.last_box
            return VLMLocateResponse(
                server_time=now,
                text=guidance_text(target_name, seed.bearing_degrees),
                target=VLMLocatedTarget(
                    label=target_name,
                    confidence=None,
                    box=VLMTargetBox(
                        x_min=box[0], y_min=box[1], x_max=box[2], y_max=box[3]
                    ),
                    point={
                        "x": remembered.last_center_x,
                        "y": (box[1] + box[3]) / 2.0,
                    },
                ),
                bearing_degrees=seed.bearing_degrees,
                range_hint=seed.range_hint,
                resolved_from="MEMORY",
                clock_direction=compatibility_clock_direction(
                    remembered.last_center_x if visible else None
                ),
                tracking_allowed=True,
                source_frame_id=snapshot.frame_id,
                timings=VLMTimings(
                    decode_ms=0.0,
                    load_ms=0.0,
                    inference_ms=0.0,
                    unload_ms=0.0,
                    total_ms=(perf_counter() - started) * 1000,
                ),
            )

    engine: VLMEngine = request.app.state.vlm_engine
    if not engine.ready:
        if session_id is not None:
            target_sessions.fail_seeking(session_id, target_name)
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM is unavailable.",
            status_code=503,
            retryable=True,
            details={"vlm": engine.detail},
        )

    source_frame_id: int | None = None
    source_heading_degrees: float | None = None
    rotation = RotationDegrees.DEG_0
    if frame is None and image_base64 is None and session_id is not None:
        frame_memory: LatestFrameMemory = request.app.state.latest_frame_memory
        snapshot = frame_memory.snapshot(session_id)
        frame_bytes = snapshot.jpeg_bytes
        rotation = snapshot.rotation_degrees
        source_frame_id = snapshot.frame_id
        source_heading_degrees = snapshot.heading_degrees
    else:
        frame_bytes = await _read_image_payload(
            frame,
            image_base64,
            max_bytes=settings.vlm_max_image_bytes,
        )

    decode_started = perf_counter()
    decoded = await run_in_threadpool(
        decode_jpeg,
        frame_bytes,
        rotation_degrees=rotation,
        max_image_width=settings.vlm_max_image_width,
        max_image_pixels=settings.vlm_max_image_pixels,
    )
    decode_ms = (perf_counter() - decode_started) * 1000
    del frame_bytes

    if session_id is not None:
        target_sessions.begin_seeking(session_id, target_name)

    executor: VLMExecutor = request.app.state.vlm_executor
    try:
        result = await executor.run(
            lambda: engine.locate(decoded.image, target_name),
            timeout_seconds=settings.vlm_timeout_seconds,
        )
    except AppError:
        if session_id is not None:
            target_sessions.fail_seeking(session_id, target_name)
        raise
    except VLMTargetNotFoundError as exc:
        if session_id is not None:
            target_sessions.fail_seeking(session_id, target_name)
        raise AppError(
            ErrorCode.NOT_FOUND,
            f"I can't find a {target_name} nearby. "
            "I can only guide you to things I can recognise.",
            status_code=404,
        ) from exc
    except VLMResourceError as exc:
        if session_id is not None:
            target_sessions.fail_seeking(session_id, target_name)
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM could not reserve safe CUDA memory.",
            status_code=503,
            retryable=True,
            details={"reason": str(exc)},
        ) from exc
    except VLMError as exc:
        if session_id is not None:
            target_sessions.fail_seeking(session_id, target_name)
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM could not locate this target.",
            status_code=503,
            retryable=True,
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        if session_id is not None:
            target_sessions.fail_seeking(session_id, target_name)
        raise AppError(
            ErrorCode.MODEL_NOT_READY,
            "The local VLM could not locate this target.",
            status_code=503,
            retryable=True,
            details={"reason": type(exc).__name__},
        ) from exc

    tracking_allowed = False
    result_range = range_hint(result.box)
    result_bearing = (result.point[0] - 0.5) * settings.walk_camera_hfov_degrees
    if session_id is not None:
        landmark = landmark_memories.remember(
            session_id,
            label=target_name,
            now_ms=now_ms,
            heading_degrees=source_heading_degrees,
            box=result.box,
        )
        seed = target_sessions.start_guidance(
            session_id,
            target_name=target_name,
            landmark=landmark,
            now_ms=now_ms,
            heading_degrees=source_heading_degrees,
            visible=True,
        )
        result_bearing = seed.bearing_degrees
        result_range = seed.range_hint
        tracking_allowed = True

    direction = compatibility_clock_direction(result.point[0])
    total_ms = (perf_counter() - started) * 1000
    return VLMLocateResponse(
        server_time=utc_now(),
        text=guidance_text(target_name, result_bearing),
        target=VLMLocatedTarget(
            label=target_name,
            confidence=result.confidence,
            box=VLMTargetBox(
                x_min=result.box[0],
                y_min=result.box[1],
                x_max=result.box[2],
                y_max=result.box[3],
            ),
            point={"x": result.point[0], "y": result.point[1]},
        ),
        bearing_degrees=result_bearing,
        range_hint=result_range,
        resolved_from="VLM",
        clock_direction=direction,
        tracking_allowed=tracking_allowed,
        source_frame_id=source_frame_id,
        timings=VLMTimings(
            decode_ms=decode_ms,
            load_ms=result.load_ms,
            inference_ms=result.inference_ms,
            unload_ms=result.unload_ms,
            total_ms=total_ms,
        ),
    )


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
