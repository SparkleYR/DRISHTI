from __future__ import annotations

import pytest

from app.errors import AppError, ErrorCode
from app.scheduling.frame_memory import LatestFrameMemory
from app.schemas.walk import RotationDegrees


def test_frame_memory_retains_only_newest_frame_and_clears_on_end() -> None:
    memory = LatestFrameMemory()
    memory.store("walk-1", 2, b"new", RotationDegrees.DEG_90)
    memory.store("walk-1", 1, b"old", RotationDegrees.DEG_0)

    snapshot = memory.snapshot("walk-1")
    assert snapshot.frame_id == 2
    assert snapshot.jpeg_bytes == b"new"
    assert snapshot.rotation_degrees == RotationDegrees.DEG_90

    memory.end_session("walk-1")
    with pytest.raises(AppError) as missing:
        memory.snapshot("walk-1")
    assert missing.value.code == ErrorCode.INVALID_REQUEST
