import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.errors import AppError, ErrorCode
from test_walk import analyze, start_session


class AlwaysSupersedeScheduler:
    async def submit(self, _session_id, frame_id, _run):
        raise AppError(
            ErrorCode.FRAME_SUPERSEDED,
            "The waiting frame was replaced by a newer frame.",
            status_code=409,
            retryable=True,
            details={"superseded_frame_id": frame_id, "newest_frame_id": frame_id + 1},
        )

    async def end_session(self, _session_id):
        return None


class DelayedScheduler:
    async def submit(self, _session_id, _frame_id, run):
        await asyncio.sleep(0.15)
        return await run()

    async def end_session(self, _session_id):
        return None


def test_superseded_frame_uses_frozen_error_contract(client: TestClient) -> None:
    client.app.state.frame_scheduler = AlwaysSupersedeScheduler()
    session = start_session(client)

    response = analyze(client, str(session["session_id"]), frame_id=4)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "FRAME_SUPERSEDED",
        "message": "The waiting frame was replaced by a newer frame.",
        "retryable": True,
        "details": {"superseded_frame_id": 4, "newest_frame_id": 5},
    }


def test_frame_that_expires_while_waiting_is_not_inferred(client: TestClient) -> None:
    client.app.state.settings.max_result_age_ms = 300
    client.app.state.frame_scheduler = DelayedScheduler()
    detector = client.app.state.detector
    session = start_session(client)
    captured_at = datetime.now(UTC) - timedelta(milliseconds=200)

    response = analyze(
        client,
        str(session["session_id"]),
        frame_id=0,
        captured_at=captured_at,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FRAME_TOO_OLD"
    assert response.json()["error"]["retryable"] is True
    assert detector.call_count == 0
