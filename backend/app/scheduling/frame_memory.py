from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from app.errors import AppError, ErrorCode
from app.schemas.walk import RotationDegrees


@dataclass(frozen=True)
class FrameSnapshot:
    session_id: str
    frame_id: int
    jpeg_bytes: bytes
    rotation_degrees: RotationDegrees


class LatestFrameMemory:
    """Keeps exactly one replaceable, process-local JPEG per active session."""

    def __init__(self) -> None:
        self._frames: dict[str, FrameSnapshot] = {}
        self._lock = RLock()

    def store(
        self,
        session_id: str,
        frame_id: int,
        jpeg_bytes: bytes,
        rotation_degrees: RotationDegrees,
    ) -> None:
        snapshot = FrameSnapshot(
            session_id=session_id,
            frame_id=frame_id,
            jpeg_bytes=bytes(jpeg_bytes),
            rotation_degrees=rotation_degrees,
        )
        with self._lock:
            current = self._frames.get(session_id)
            if current is None or frame_id > current.frame_id:
                self._frames[session_id] = snapshot

    def snapshot(self, session_id: str) -> FrameSnapshot:
        with self._lock:
            current = self._frames.get(session_id)
            if current is None:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "No walking frame is available for this active session yet.",
                    status_code=409,
                    retryable=True,
                )
            return FrameSnapshot(
                session_id=current.session_id,
                frame_id=current.frame_id,
                jpeg_bytes=bytes(current.jpeg_bytes),
                rotation_degrees=current.rotation_degrees,
            )

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._frames.pop(session_id, None)
