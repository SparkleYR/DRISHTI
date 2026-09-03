from __future__ import annotations

import asyncio
import threading

import pytest

from app.errors import AppError, ErrorCode
from app.explore.local_vlm import VLMError, _answer_text, _location_geometry
from app.explore.vlm_executor import VLMExecutor


def test_vlm_answer_shape_is_normalized() -> None:
    assert _answer_text({"answer": "  A chair\n is ahead.  "}) == "A chair is ahead."
    assert _answer_text("  A desk is visible.  ") == "A desk is visible."
    with pytest.raises(VLMError):
        _answer_text({"caption": "unsupported"})


def test_vlm_location_selects_largest_valid_normalized_box() -> None:
    box, point = _location_geometry(
        {
            "objects": [
                {"x_min": 0.05, "y_min": 0.10, "x_max": 0.15, "y_max": 0.20},
                {"x_min": 0.20, "y_min": 0.30, "x_max": 0.50, "y_max": 0.80},
                {"x_min": 0.7, "y_min": 0.7, "x_max": 0.6, "y_max": 0.8},
            ]
        }
    )
    assert box == (0.20, 0.30, 0.50, 0.80)
    assert point == pytest.approx((0.35, 0.55))


def test_vlm_executor_rejects_waiting_work_and_releases_after_completion() -> None:
    async def scenario() -> None:
        executor = VLMExecutor()
        started = threading.Event()
        release = threading.Event()

        def blocking() -> str:
            started.set()
            release.wait(timeout=5)
            return "answer"

        first = asyncio.create_task(
            executor.run(blocking, timeout_seconds=5)
        )
        await asyncio.to_thread(started.wait, 5)
        with pytest.raises(AppError) as busy:
            await executor.run(lambda: "queued", timeout_seconds=5)
        assert busy.value.code == ErrorCode.CONFLICT
        release.set()
        assert await first == "answer"
        assert await executor.run(lambda: "next", timeout_seconds=5) == "next"
        executor.shutdown()

    asyncio.run(scenario())


def test_vlm_timeout_does_not_create_a_second_worker() -> None:
    async def scenario() -> None:
        executor = VLMExecutor()
        release = threading.Event()

        with pytest.raises(AppError) as timed_out:
            await executor.run(
                lambda: release.wait(timeout=5),
                timeout_seconds=0.01,
            )
        assert timed_out.value.code == ErrorCode.REQUEST_TIMEOUT
        with pytest.raises(AppError) as busy:
            await executor.run(lambda: "queued", timeout_seconds=1)
        assert busy.value.code == ErrorCode.CONFLICT
        release.set()
        await asyncio.sleep(0.05)
        assert await executor.run(lambda: "recovered", timeout_seconds=1) == "recovered"
        executor.shutdown()

    asyncio.run(scenario())
