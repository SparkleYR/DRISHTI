from __future__ import annotations

import asyncio

from app.schemas.walk import TargetTelemetryEvent


class LatestTelemetryHub:
    """Bounded fan-out: each subscriber retains only the newest event."""

    def __init__(self) -> None:
        self._subscribers: dict[
            str, set[asyncio.Queue[TargetTelemetryEvent | None]]
        ] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, session_id: str
    ) -> asyncio.Queue[TargetTelemetryEvent | None]:
        queue: asyncio.Queue[TargetTelemetryEvent | None] = asyncio.Queue(maxsize=1)
        async with self._lock:
            self._subscribers.setdefault(session_id, set()).add(queue)
        return queue

    async def unsubscribe(
        self,
        session_id: str,
        queue: asyncio.Queue[TargetTelemetryEvent | None],
    ) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(session_id)
            if subscribers is None:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(session_id, None)

    async def publish(self, event: TargetTelemetryEvent) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers.get(event.session_id, ()))
        for queue in subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def end_session(self, session_id: str) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers.pop(session_id, ()))
        for queue in subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(None)
