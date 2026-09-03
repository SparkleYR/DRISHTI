from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel, SCHEMA_VERSION


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
