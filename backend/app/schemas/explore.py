from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import ApiModel, SCHEMA_VERSION
from app.schemas.walk import NonNegativeMilliseconds, Normalized


class ExploreMode(StrEnum):
    READ_TEXT = "READ_TEXT"


class OcrConfidenceQualification(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"
    NONE = "NONE"


class ExploreTimings(ApiModel):
    decode_ms: NonNegativeMilliseconds
    ocr_ms: NonNegativeMilliseconds
    total_ms: NonNegativeMilliseconds


class ReadTextResponse(ApiModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    server_time: datetime
    mode: Literal["READ_TEXT"] = ExploreMode.READ_TEXT
    language: Literal["eng"] = "eng"
    text: str
    route_numbers: list[Annotated[str, Field(min_length=1, max_length=8)]]
    confidence: Normalized
    confidence_qualification: OcrConfidenceQualification
    message: str
    no_text_found: bool
    timings: ExploreTimings
