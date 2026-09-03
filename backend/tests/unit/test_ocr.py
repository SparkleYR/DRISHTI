import asyncio
import threading

import pytest

from app.errors import AppError, ErrorCode
from app.explore.executor import ExploreExecutor
from app.explore.ocr import extract_route_numbers


def test_route_number_extraction_is_ordered_and_deduplicated() -> None:
    assert extract_route_numbers("Bus 42A to Central. Route 17, then 42a.") == [
        "42A",
        "17",
    ]


def test_explore_executor_rejects_a_waiting_request() -> None:
    async def scenario() -> None:
        executor = ExploreExecutor()
        started = threading.Event()
        release = threading.Event()

        def blocking() -> str:
            started.set()
            release.wait(timeout=5)
            return "read"

        first = asyncio.create_task(executor.run(blocking))
        await asyncio.to_thread(started.wait, 5)
        with pytest.raises(AppError) as busy:
            await executor.run(lambda: "queued")
        assert busy.value.code == ErrorCode.CONFLICT
        assert busy.value.retryable is True
        release.set()
        assert await first == "read"
        executor.shutdown()

    asyncio.run(scenario())
