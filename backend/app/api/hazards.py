from __future__ import annotations

import json
from copy import deepcopy
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.frame_ingress import JPEG_CONTENT_TYPE, decode_jpeg
from app.hazards.service import HazardService
from app.schemas.hazards import (
    CreateHazardRequest,
    HazardListResponse,
    HazardResponse,
    HazardStatus,
    MergeHazardRequest,
    MergeHazardResponse,
    UpdateHazardStatusRequest,
    UpdateHazardStatusResponse,
)
from app.schemas.walk import RotationDegrees


router = APIRouter(prefix="/api/v1/hazards", tags=["hazards"])


def _inline_json_schema(schema: dict) -> dict:
    definitions = schema.pop("$defs", {})

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.rsplit("/", 1)[-1]
            replacement = deepcopy(definitions[name])
            replacement.update({key: item for key, item in value.items() if key != "$ref"})
            return expand(replacement)
        return {key: expand(item) for key, item in value.items()}

    return expand(schema)


CREATE_HAZARD_JSON_SCHEMA = _inline_json_schema(
    CreateHazardRequest.model_json_schema()
)


@router.post(
    "",
    response_model=HazardResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": CREATE_HAZARD_JSON_SCHEMA
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["payload"],
                        "properties": {
                            "payload": {
                                "type": "string",
                                "description": "CreateHazardRequest encoded as JSON.",
                            },
                            "evidence": {"type": "string", "format": "binary"},
                        },
                    }
                },
            },
        }
    },
)
async def create_hazard(request: Request) -> HazardResponse:
    payload, evidence = await _read_create_request(request)
    settings: Settings = request.app.state.settings
    evidence_bytes: bytes | None = None
    if evidence is not None:
        if not payload.evidence_consent:
            await evidence.close()
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "Evidence requires explicit consent.",
                status_code=422,
            )
        if evidence.content_type != JPEG_CONTENT_TYPE:
            await evidence.close()
            raise AppError(
                ErrorCode.INVALID_CONTENT_TYPE,
                "Hazard evidence must use image/jpeg.",
                status_code=415,
            )
        if getattr(evidence.file, "_rolled", False):
            await evidence.close()
            raise AppError(
                ErrorCode.IMAGE_TOO_LARGE,
                "Hazard evidence exceeded the local in-memory boundary.",
                status_code=413,
            )
        evidence_bytes = await evidence.read(settings.max_evidence_image_bytes + 1)
        await evidence.close()
        if len(evidence_bytes) > settings.max_evidence_image_bytes:
            raise AppError(
                ErrorCode.IMAGE_TOO_LARGE,
                "Hazard evidence exceeds the local byte limit.",
                status_code=413,
                details={
                    "max_evidence_image_bytes": settings.max_evidence_image_bytes
                },
            )
        decoded = await run_in_threadpool(
            decode_jpeg,
            evidence_bytes,
            rotation_degrees=RotationDegrees.DEG_0,
            max_image_width=settings.max_image_width,
            max_image_pixels=settings.max_image_pixels,
        )
        del decoded

    service: HazardService = request.app.state.hazard_service
    return await run_in_threadpool(service.create, payload, evidence_bytes)


@router.get("", response_model=HazardListResponse)
def list_hazards(
    request: Request,
    status: Annotated[list[HazardStatus] | None, Query()] = None,
    active: bool = False,
    category: Annotated[str | None, Query(min_length=1, max_length=96)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> HazardListResponse:
    if active and status:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "Use either active=true or explicit status filters, not both.",
            status_code=422,
        )
    service: HazardService = request.app.state.hazard_service
    return service.list(
        statuses=status,
        active=active,
        category=category,
        limit=limit,
        cursor=cursor,
    )


@router.get("/nearby", response_model=HazardListResponse)
def nearby_hazards(
    request: Request,
    map_id: str | None = None,
    map_version: str | None = None,
    map_x: Annotated[float | None, Query(ge=0, le=1)] = None,
    map_y: Annotated[float | None, Query(ge=0, le=1)] = None,
    radius: Annotated[float | None, Query(gt=0, le=2)] = None,
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_m: Annotated[float | None, Query(gt=0, le=100_000)] = None,
) -> HazardListResponse:
    map_values = (map_id, map_version, map_x, map_y, radius)
    geo_values = (latitude, longitude, radius_m)
    has_map = any(value is not None for value in map_values)
    has_geo = any(value is not None for value in geo_values)
    if has_map == has_geo or (has_map and not all(value is not None for value in map_values)) or (
        has_geo and not all(value is not None for value in geo_values)
    ):
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "Provide one complete map-coordinate or geographic-coordinate query.",
            status_code=422,
        )

    service: HazardService = request.app.state.hazard_service
    if has_map:
        assert map_id is not None and map_version is not None
        assert map_x is not None and map_y is not None and radius is not None
        return service.nearby_map(
            map_id=map_id,
            map_version=map_version,
            x=map_x,
            y=map_y,
            radius=radius,
        )
    assert latitude is not None and longitude is not None and radius_m is not None
    return service.nearby_geo(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
    )


@router.patch("/{hazard_id}/status", response_model=UpdateHazardStatusResponse)
def update_hazard_status(
    hazard_id: str,
    payload: UpdateHazardStatusRequest,
    request: Request,
) -> UpdateHazardStatusResponse:
    service: HazardService = request.app.state.hazard_service
    return service.update_status(hazard_id, payload)


@router.post("/{hazard_id}/merge", response_model=MergeHazardResponse)
def merge_hazards(
    hazard_id: str,
    payload: MergeHazardRequest,
    request: Request,
) -> MergeHazardResponse:
    service: HazardService = request.app.state.hazard_service
    return service.merge(hazard_id, payload)


async def _read_create_request(
    request: Request,
) -> tuple[CreateHazardRequest, UploadFile | None]:
    content_type = request.headers.get("content-type", "").lower()
    try:
        if content_type.startswith("application/json"):
            return CreateHazardRequest.model_validate(await request.json()), None
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            raw_payload = form.get("payload")
            if not isinstance(raw_payload, str):
                raise ValueError("missing payload part")
            payload = CreateHazardRequest.model_validate_json(raw_payload)
            raw_evidence = form.get("evidence")
            evidence = raw_evidence if isinstance(raw_evidence, UploadFile) else None
            return payload, evidence
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "The hazard report did not match the API contract.",
            status_code=422,
        ) from exc
    raise AppError(
        ErrorCode.INVALID_CONTENT_TYPE,
        "Hazard reports require application/json or multipart/form-data.",
        status_code=415,
    )
