from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.errors import AppError, ErrorCode


ResultT = TypeVar("ResultT")


class ExploreExecutor:
    """Runs one CPU OCR request without allowing a waiting queue."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="drishti-ocr",
        )
        self._state_lock = asyncio.Lock()
        self._busy = False

    async def run(self, operation: Callable[[], ResultT]) -> ResultT:
        async with self._state_lock:
            if self._busy:
                raise AppError(
                    ErrorCode.CONFLICT,
                    "The local OCR worker is busy. Retry the one-shot request.",
                    status_code=409,
                    retryable=True,
                )
            self._busy = True
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._pool, operation)
        try:
            return await asyncio.shield(future)
        finally:
            if future.done():
                await self._release()
            else:
                future.add_done_callback(
                    lambda _future: loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._release())
                    )
                )

    async def _release(self) -> None:
        async with self._state_lock:
            self._busy = False

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
