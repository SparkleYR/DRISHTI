from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


SCHEMA_VERSION = "1.0.0"


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def utc_now() -> datetime:
    return datetime.now(UTC)
