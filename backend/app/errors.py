from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import SCHEMA_VERSION


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_CONTENT_TYPE = "INVALID_CONTENT_TYPE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    IMAGE_DECODE_FAILED = "IMAGE_DECODE_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_ENDED = "SESSION_ENDED"
    FRAME_ID_NOT_MONOTONIC = "FRAME_ID_NOT_MONOTONIC"
    FRAME_TOO_OLD = "FRAME_TOO_OLD"
    FRAME_SUPERSEDED = "FRAME_SUPERSEDED"
    MODEL_NOT_READY = "MODEL_NOT_READY"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    INVALID_STATUS_TRANSITION = "INVALID_STATUS_TRANSITION"
    CONFLICT = "CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    retryable: bool
    details: dict[str, Any] | None = None


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    server_time: datetime
    error: ErrorDetail


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details


def utc_now() -> datetime:
    return datetime.now(UTC)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        response = ApiErrorResponse(
            server_time=utc_now(),
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            ),
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        is_not_found = exc.status_code == 404
        response = ApiErrorResponse(
            server_time=utc_now(),
            error=ErrorDetail(
                code=ErrorCode.NOT_FOUND if is_not_found else ErrorCode.INVALID_REQUEST,
                message="The requested local resource was not found."
                if is_not_found
                else "The request could not be completed.",
                retryable=False,
            ),
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_errors = [
            {
                "loc": list(error["loc"]),
                "msg": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        response = ApiErrorResponse(
            server_time=utc_now(),
            error=ErrorDetail(
                code=ErrorCode.INVALID_REQUEST,
                message="The request did not match the API contract.",
                retryable=False,
                details={"errors": safe_errors},
            ),
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))
