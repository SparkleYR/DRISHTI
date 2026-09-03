from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from app.errors import AppError, ErrorCode


ResultT = TypeVar("ResultT")


@dataclass
class _Job(Generic[ResultT]):
    frame_id: int
    run: Callable[[], Awaitable[ResultT]]
    result: asyncio.Future[ResultT]


@dataclass
class _SessionQueue(Generic[ResultT]):
    active: bool = False
    waiting: _Job[ResultT] | None = None
    idle: asyncio.Event = field(default_factory=asyncio.Event)


class LatestFrameScheduler(Generic[ResultT]):
    """Runs one job per session and retains only the newest waiting job."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionQueue[ResultT]] = {}
        self._ended_sessions: set[str] = set()
        self._lock = asyncio.Lock()

    async def submit(
        self,
        session_id: str,
        frame_id: int,
        run: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        loop = asyncio.get_running_loop()
        job = _Job(frame_id=frame_id, run=run, result=loop.create_future())
        start_now = False
        superseded: _Job[ResultT] | None = None
        async with self._lock:
            if session_id in self._ended_sessions:
                raise _session_ended_error()
            queue = self._sessions.setdefault(session_id, _SessionQueue())
            if not queue.active:
                queue.active = True
                queue.idle.clear()
                start_now = True
            else:
                superseded = queue.waiting
                queue.waiting = job

        if superseded is not None and not superseded.result.done():
            superseded.result.set_exception(
                AppError(
                    ErrorCode.FRAME_SUPERSEDED,
                    "The waiting frame was replaced by a newer frame.",
                    status_code=409,
                    retryable=True,
                    details={
                        "superseded_frame_id": superseded.frame_id,
                        "newest_frame_id": frame_id,
                    },
                )
            )
        if start_now:
            asyncio.create_task(self._drain(session_id, job))
        return await job.result

    async def end_session(self, session_id: str) -> None:
        waiting: _Job[ResultT] | None = None
        idle: asyncio.Event | None = None
        async with self._lock:
            self._ended_sessions.add(session_id)
            queue = self._sessions.get(session_id)
            if queue is not None:
                waiting = queue.waiting
                queue.waiting = None
                if queue.active:
                    idle = queue.idle
                else:
                    self._sessions.pop(session_id, None)
        if waiting is not None and not waiting.result.done():
            waiting.result.set_exception(_session_ended_error())
        if idle is not None:
            await idle.wait()

    async def _drain(self, session_id: str, first: _Job[ResultT]) -> None:
        current: _Job[ResultT] | None = first
        while current is not None:
            if not current.result.cancelled():
                try:
                    output = await current.run()
                except Exception as exc:
                    if not current.result.done():
                        current.result.set_exception(exc)
                else:
                    if not current.result.done():
                        current.result.set_result(output)

            async with self._lock:
                queue = self._sessions.get(session_id)
                if queue is None:
                    return
                current = queue.waiting
                queue.waiting = None
                if current is None:
                    queue.active = False
                    queue.idle.set()
                    self._sessions.pop(session_id, None)


def _session_ended_error() -> AppError:
    return AppError(
        ErrorCode.SESSION_ENDED,
        "The walking session has ended.",
        status_code=409,
    )
