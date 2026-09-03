from __future__ import annotations

from collections.abc import Awaitable, Callable
from starlette.types import Message, Receive, Scope, Send

from app.errors import ApiErrorResponse, ErrorCode, ErrorDetail, utc_now


class AnalyzeBodyLimitMiddleware:
    """Buffer selected image requests so multipart bytes never roll to disk."""

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        max_body_bytes: int,
        paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.paths = paths or {"/api/v1/walk/analyze"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                await self._send_too_large(send)
                return
            body.extend(chunk)
            more_body = message.get("more_body", False)

        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    async def _send_too_large(self, send: Send) -> None:
        from fastapi.responses import JSONResponse

        payload = ApiErrorResponse(
            server_time=utc_now(),
            error=ErrorDetail(
                code=ErrorCode.IMAGE_TOO_LARGE,
                message="The multipart upload exceeds the local request limit.",
                retryable=False,
            ),
        )
        response = JSONResponse(
            status_code=413,
            content=payload.model_dump(mode="json"),
        )
        await response({"type": "http"}, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}
