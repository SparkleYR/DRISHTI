from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from app.schemas.common import ApiModel, SCHEMA_VERSION


class ServiceStatus(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ModuleStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    LOADING = "LOADING"


class ComputeDevice(StrEnum):
    CUDA = "CUDA"
    CPU = "CPU"
    NONE = "NONE"


class ModuleHealth(ApiModel):
    status: ModuleStatus
    detail: str | None = None


class ServiceInfo(ApiModel):
    name: Literal["drishti-backend"] = "drishti-backend"
    version: str


class ComputeInfo(ApiModel):
    selected_device: ComputeDevice
    device_name: str | None = None


class ModelHealth(ApiModel):
    detector: ModuleHealth
    segmentation: ModuleHealth
    tracker: ModuleHealth
    depth: ModuleHealth
    india_hazards: ModuleHealth
    ocr: ModuleHealth
    vlm: ModuleHealth


class HealthResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    status: ServiceStatus
    runtime_mode: Literal["LOCAL_ONLY"] = "LOCAL_ONLY"
    service: ServiceInfo
    compute: ComputeInfo
    models: ModelHealth
    database: ModuleHealth
    walk_mode_available: bool
