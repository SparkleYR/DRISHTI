from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Protocol

import cv2
import numpy as np

from app.schemas.walk import (
    NormalizedPoint,
    TargetHapticPattern,
    TargetTrackingState,
    TargetTrackingTelemetry,
)


NormalizedBox = tuple[float, float, float, float]


class OpenCVTracker(Protocol):
    def init(self, image: np.ndarray, box: tuple[int, int, int, int]) -> object: ...

    def update(
        self, image: np.ndarray
    ) -> tuple[bool, tuple[float, float, float, float]]: ...


@dataclass
class _TargetSession:
    state: TargetTrackingState = TargetTrackingState.IDLE
    target_name: str | None = None
    tracker: OpenCVTracker | None = None
    box: NormalizedBox | None = None
    confidence: float | None = None
    reference_histogram: np.ndarray | None = None
    last_announced_direction: str | None = None
    lost_announcement_pending: bool = False


class TargetTrackingSessionStore:
    """Session-scoped VLM-to-OpenCV target handoff with no frame persistence."""

    def __init__(
        self,
        *,
        confidence_threshold: float,
        tracker_factory: Callable[[], OpenCVTracker] | None = None,
    ) -> None:
        self._confidence_threshold = confidence_threshold
        self._tracker_factory = tracker_factory or cv2.TrackerMIL_create
        self._sessions: dict[str, _TargetSession] = {}
        self._lock = RLock()

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = _TargetSession()

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def begin_locating(self, session_id: str, target_name: str) -> None:
        with self._lock:
            session = self._sessions.setdefault(session_id, _TargetSession())
            session.state = TargetTrackingState.LOCATING
            session.target_name = target_name
            session.tracker = None
            session.box = None
            session.confidence = None
            session.reference_histogram = None
            session.last_announced_direction = None
            session.lost_announcement_pending = False

    def fail_locating(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.setdefault(session_id, _TargetSession())
            session.state = TargetTrackingState.TARGET_LOST
            session.tracker = None
            session.box = None
            session.confidence = None
            session.reference_histogram = None
            session.lost_announcement_pending = True

    def lock_target(
        self,
        session_id: str,
        target_name: str,
        image: np.ndarray,
        box: NormalizedBox,
    ) -> bool:
        pixel_box = _to_pixel_box(box, image)
        if pixel_box is None:
            self.fail_locating(session_id)
            return False
        try:
            tracker = self._tracker_factory()
            initialized = tracker.init(image, pixel_box)
        except (cv2.error, AttributeError, TypeError, ValueError):
            self.fail_locating(session_id)
            return False
        if initialized is False:
            self.fail_locating(session_id)
            return False

        reference = _appearance_histogram(image, pixel_box)
        if reference is None:
            self.fail_locating(session_id)
            return False

        with self._lock:
            session = self._sessions.setdefault(session_id, _TargetSession())
            session.state = TargetTrackingState.LOCKED_TRACKING
            session.target_name = target_name
            session.tracker = tracker
            session.box = box
            session.confidence = 1.0
            session.reference_histogram = reference
            session.last_announced_direction = None
            session.lost_announcement_pending = False
        return True

    def update(self, session_id: str, image: np.ndarray) -> None:
        with self._lock:
            session = self._sessions.setdefault(session_id, _TargetSession())
            if (
                session.state != TargetTrackingState.LOCKED_TRACKING
                or session.tracker is None
                or session.reference_histogram is None
            ):
                return
            try:
                tracked, pixel_box = session.tracker.update(image)
            except (cv2.error, AttributeError, TypeError, ValueError):
                tracked = False
                pixel_box = (0.0, 0.0, 0.0, 0.0)
            normalized = _to_normalized_box(pixel_box, image) if tracked else None
            integer_box = _clamp_pixel_box(pixel_box, image) if tracked else None
            current_histogram = (
                _appearance_histogram(image, integer_box)
                if integer_box is not None
                else None
            )
            confidence = (
                _appearance_confidence(
                    session.reference_histogram,
                    current_histogram,
                )
                if current_histogram is not None
                else 0.0
            )
            if normalized is None or confidence < self._confidence_threshold:
                session.state = TargetTrackingState.TARGET_LOST
                session.tracker = None
                session.box = None
                session.confidence = confidence
                session.reference_histogram = None
                session.lost_announcement_pending = True
                return
            session.box = normalized
            session.confidence = confidence

    def telemetry(
        self,
        session_id: str,
        *,
        is_safety_overridden: bool,
        haptics_enabled: bool,
    ) -> TargetTrackingTelemetry:
        with self._lock:
            session = self._sessions.setdefault(session_id, _TargetSession())
            centre = _box_centre(session.box) if session.box is not None else None
            direction = clock_direction(centre[0]) if centre is not None else None
            speech = ""
            speak = False
            haptic = TargetHapticPattern.NONE

            if not is_safety_overridden:
                if (
                    session.state == TargetTrackingState.TARGET_LOST
                    and session.lost_announcement_pending
                ):
                    speech = "Target lost. Stop and scan again."
                    speak = True
                    session.lost_announcement_pending = False
                elif (
                    session.state == TargetTrackingState.LOCKED_TRACKING
                    and direction is not None
                    and direction != session.last_announced_direction
                ):
                    speech = f"Target at {direction}."
                    speak = True
                    session.last_announced_direction = direction
                    if haptics_enabled:
                        haptic = _target_haptic(centre[0])

            return TargetTrackingTelemetry(
                tracking_state=session.state,
                target_name=session.target_name,
                clock_direction=direction,
                target_center=(
                    NormalizedPoint(x=centre[0], y=centre[1])
                    if centre is not None
                    else None
                ),
                confidence=session.confidence,
                is_safety_overridden=is_safety_overridden,
                speech=speech,
                speak=speak,
                haptic_pattern=haptic,
            )


def clock_direction(x: float) -> str:
    if x < 0.20:
        hour = 9
    elif x < 0.35:
        hour = 10
    elif x < 0.45:
        hour = 11
    elif x < 0.55:
        hour = 12
    elif x < 0.65:
        hour = 1
    elif x < 0.80:
        hour = 2
    else:
        hour = 3
    return f"{hour} o'clock"


def _to_pixel_box(box: NormalizedBox, image: np.ndarray) -> tuple[int, int, int, int] | None:
    height, width = image.shape[:2]
    x_min, y_min, x_max, y_max = box
    return _clamp_pixel_box(
        (
            x_min * width,
            y_min * height,
            (x_max - x_min) * width,
            (y_max - y_min) * height,
        ),
        image,
    )


def _clamp_pixel_box(
    box: tuple[float, float, float, float], image: np.ndarray
) -> tuple[int, int, int, int] | None:
    height, width = image.shape[:2]
    x, y, box_width, box_height = box
    left = max(0, min(width - 1, int(round(x))))
    top = max(0, min(height - 1, int(round(y))))
    right = max(left + 1, min(width, int(round(x + box_width))))
    bottom = max(top + 1, min(height, int(round(y + box_height))))
    if right - left < 2 or bottom - top < 2:
        return None
    return left, top, right - left, bottom - top


def _to_normalized_box(
    box: tuple[float, float, float, float], image: np.ndarray
) -> NormalizedBox | None:
    integer_box = _clamp_pixel_box(box, image)
    if integer_box is None:
        return None
    height, width = image.shape[:2]
    x, y, box_width, box_height = integer_box
    return (
        x / width,
        y / height,
        (x + box_width) / width,
        (y + box_height) / height,
    )


def _appearance_histogram(
    image: np.ndarray,
    box: tuple[int, int, int, int] | None,
) -> np.ndarray | None:
    if box is None:
        return None
    x, y, width, height = box
    crop = image[y : y + height, x : x + width]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    return cv2.normalize(histogram, None, alpha=1.0, norm_type=cv2.NORM_L1)


def _appearance_confidence(reference: np.ndarray, current: np.ndarray) -> float:
    distance = float(cv2.compareHist(reference, current, cv2.HISTCMP_BHATTACHARYYA))
    return max(0.0, min(1.0, 1.0 - distance))


def _box_centre(box: NormalizedBox) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _target_haptic(x: float) -> TargetHapticPattern:
    if x < 0.45:
        return TargetHapticPattern.TARGET_LEFT_PULSE
    if x > 0.55:
        return TargetHapticPattern.TARGET_RIGHT_PULSE
    return TargetHapticPattern.TARGET_CENTRE_PULSE
