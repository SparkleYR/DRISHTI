import asyncio

import pytest

from app.errors import AppError, ErrorCode
from app.scheduling.latest_frame import LatestFrameScheduler


def test_latest_frame_scheduler_keeps_one_active_and_one_waiting() -> None:
    async def scenario() -> None:
        scheduler = LatestFrameScheduler[str]()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        calls: list[int] = []
        active = 0
        max_active = 0

        async def run(frame_id: int, *, block: bool = False) -> str:
            nonlocal active, max_active
            calls.append(frame_id)
            active += 1
            max_active = max(max_active, active)
            if block:
                first_started.set()
                await release_first.wait()
            active -= 1
            return f"frame-{frame_id}"

        first = asyncio.create_task(
            scheduler.submit("session", 0, lambda: run(0, block=True))
        )
        await first_started.wait()
        waiting = asyncio.create_task(
            scheduler.submit("session", 1, lambda: run(1))
        )
        await asyncio.sleep(0)
        newest = asyncio.create_task(
            scheduler.submit("session", 2, lambda: run(2))
        )
        await asyncio.sleep(0)

        with pytest.raises(AppError) as superseded:
            await waiting
        assert superseded.value.code == ErrorCode.FRAME_SUPERSEDED
        assert superseded.value.details == {
            "superseded_frame_id": 1,
            "newest_frame_id": 2,
        }

        release_first.set()
        assert await first == "frame-0"
        assert await newest == "frame-2"
        assert calls == [0, 2]
        assert max_active == 1

    asyncio.run(scenario())


def test_ending_session_rejects_waiting_and_future_jobs() -> None:
    async def scenario() -> None:
        scheduler = LatestFrameScheduler[str]()
        started = asyncio.Event()
        release = asyncio.Event()

        async def active() -> str:
            started.set()
            await release.wait()
            return "finished"

        first = asyncio.create_task(scheduler.submit("session", 0, active))
        await started.wait()
        waiting = asyncio.create_task(
            scheduler.submit("session", 1, lambda: asyncio.sleep(0, result="late"))
        )
        await asyncio.sleep(0)
        ending = asyncio.create_task(scheduler.end_session("session"))
        await asyncio.sleep(0)

        with pytest.raises(AppError) as ended_waiting:
            await waiting
        assert ended_waiting.value.code == ErrorCode.SESSION_ENDED
        with pytest.raises(AppError) as ended_future:
            await scheduler.submit(
                "session",
                2,
                lambda: asyncio.sleep(0, result="never"),
            )
        assert ended_future.value.code == ErrorCode.SESSION_ENDED

        release.set()
        assert await first == "finished"
        await ending

    asyncio.run(scenario())
