from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from uuid import uuid4

from app.errors import AppError, ErrorCode
from app.schemas.walk import StartWalkSessionRequest


@dataclass
class WalkSession:
    session_id: str
    started_at: datetime
    request: StartWalkSessionRequest
    ended_at: datetime | None = None
    last_frame_id: int = -1


class WalkSessionStore:
    """Process-local Phase 1 session state; it stores metadata, never frame bytes."""

    def __init__(self) -> None:
        self._sessions: dict[str, WalkSession] = {}
        self._lock = RLock()

    def start(self, request: StartWalkSessionRequest, started_at: datetime) -> WalkSession:
        session = WalkSession(
            session_id=str(uuid4()),
            started_at=started_at,
            request=request,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def require_active(self, session_id: str) -> WalkSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise AppError(
                    ErrorCode.SESSION_NOT_FOUND,
                    "The walking session was not found.",
                    status_code=404,
                )
            if session.ended_at is not None:
                raise AppError(
                    ErrorCode.SESSION_ENDED,
                    "The walking session has ended.",
                    status_code=409,
                )
            return session

    def accept_frame_id(self, session_id: str, frame_id: int) -> None:
        with self._lock:
            session = self.require_active(session_id)
            if frame_id <= session.last_frame_id:
                raise AppError(
                    ErrorCode.FRAME_ID_NOT_MONOTONIC,
                    "Frame IDs must increase within a walking session.",
                    status_code=409,
                    details={"last_frame_id": session.last_frame_id},
                )
            session.last_frame_id = frame_id

    def end(self, session_id: str, ended_at: datetime) -> WalkSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise AppError(
                    ErrorCode.SESSION_NOT_FOUND,
                    "The walking session was not found.",
                    status_code=404,
                )
            if session.ended_at is None:
                session.ended_at = ended_at
            return session
