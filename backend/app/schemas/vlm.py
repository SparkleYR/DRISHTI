from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, SCHEMA_VERSION
from app.schemas.walk import NormalizedPoint


class VLMTimings(ApiModel):
    decode_ms: float = Field(ge=0)
    load_ms: float = Field(ge=0)
    inference_ms: float = Field(ge=0)
    unload_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class VLMQueryResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    model: Literal["moondream2"] = "moondream2"
    text: str
    timings: VLMTimings


class VLMTargetBox(ApiModel):
    x_min: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    y_min: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    x_max: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    y_max: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_order(self) -> "VLMTargetBox":
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("bounding-box minimums must be below maximums")
        return self


class VLMLocatedTarget(ApiModel):
    label: str = Field(min_length=1, max_length=120)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    box: VLMTargetBox
    point: NormalizedPoint


class VLMLocateResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    model: Literal["moondream2"] = "moondream2"
    text: str
    target: VLMLocatedTarget
    clock_direction: str
    tracking_allowed: bool
    source_frame_id: int | None = Field(default=None, ge=0)
    timings: VLMTimings
