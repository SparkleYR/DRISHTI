from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import hypot
from threading import Lock

from app.perception.detector import DetectionCandidate


@dataclass(frozen=True)
class TrackedDetection:
    detection: DetectionCandidate
    track_id: int
    approach_rate: float | None
    area_change: float | None
    motion_dx: float | None
    motion_dy: float | None


@dataclass
class _Track:
    track_id: int
    label: str
    detection: DetectionCandidate
    first_seen: datetime
    last_seen: datetime
    last_frame_id: int


class SessionTracker:
    def __init__(
        self,
        *,
        iou_threshold: float,
        centre_distance_threshold: float,
        max_age_frames: int,
    ) -> None:
        self._iou_threshold = iou_threshold
        self._centre_distance_threshold = centre_distance_threshold
        self._max_age_frames = max_age_frames
        self._tracks: dict[int, _Track] = {}
        self._next_track_id = 1

    def update(
        self,
        detections: list[DetectionCandidate],
        *,
        frame_id: int,
        captured_at: datetime,
    ) -> list[TrackedDetection]:
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if frame_id - track.last_frame_id <= self._max_age_frames
        }
        available_tracks = set(self._tracks)
        output: list[TrackedDetection] = []

        for detection in detections:
            track = self._best_match(detection, available_tracks)
            if track is None:
                track = _Track(
                    track_id=self._next_track_id,
                    label=detection.label,
                    detection=detection,
                    first_seen=captured_at,
                    last_seen=captured_at,
                    last_frame_id=frame_id,
                )
                self._next_track_id += 1
                self._tracks[track.track_id] = track
                output.append(
                    TrackedDetection(
                        detection=detection,
                        track_id=track.track_id,
                        approach_rate=None,
                        area_change=None,
                        motion_dx=None,
                        motion_dy=None,
                    )
                )
                continue

            available_tracks.remove(track.track_id)
            previous = track.detection
            previous_area = _area(previous)
            current_area = _area(detection)
            area_change = (current_area - previous_area) / max(previous_area, 1e-6)
            previous_centre = _centre(previous)
            current_centre = _centre(detection)
            output.append(
                TrackedDetection(
                    detection=detection,
                    track_id=track.track_id,
                    approach_rate=min(1.0, max(0.0, area_change)),
                    area_change=area_change,
                    motion_dx=current_centre[0] - previous_centre[0],
                    motion_dy=current_centre[1] - previous_centre[1],
                )
            )
            track.detection = detection
            track.last_seen = captured_at
            track.last_frame_id = frame_id

        return output

    def _best_match(
        self,
        detection: DetectionCandidate,
        available_track_ids: set[int],
    ) -> _Track | None:
        best: tuple[float, _Track] | None = None
        for track_id in available_track_ids:
            track = self._tracks[track_id]
            if track.label != detection.label:
                continue
            overlap = _iou(track.detection, detection)
            distance = _centre_distance(track.detection, detection)
            if (
                overlap < self._iou_threshold
                and distance > self._centre_distance_threshold
            ):
                continue
            score = overlap + max(
                0.0,
                1.0 - distance / self._centre_distance_threshold,
            ) * 0.1
            if best is None or score > best[0]:
                best = (score, track)
        return best[1] if best else None


class TrackingSessionStore:
    def __init__(
        self,
        *,
        iou_threshold: float,
        centre_distance_threshold: float,
        max_age_frames: int,
    ) -> None:
        self._tracker_settings = {
            "iou_threshold": iou_threshold,
            "centre_distance_threshold": centre_distance_threshold,
            "max_age_frames": max_age_frames,
        }
        self._sessions: dict[str, SessionTracker] = {}
        self._lock = Lock()

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = SessionTracker(**self._tracker_settings)

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def update(
        self,
        session_id: str,
        detections: list[DetectionCandidate],
        *,
        frame_id: int,
        captured_at: datetime,
    ) -> list[TrackedDetection]:
        with self._lock:
            tracker = self._sessions.setdefault(
                session_id,
                SessionTracker(**self._tracker_settings),
            )
            return tracker.update(
                detections,
                frame_id=frame_id,
                captured_at=captured_at,
            )


def _area(detection: DetectionCandidate) -> float:
    return (detection.x2 - detection.x1) * (detection.y2 - detection.y1)


def _centre(detection: DetectionCandidate) -> tuple[float, float]:
    return (
        (detection.x1 + detection.x2) / 2,
        (detection.y1 + detection.y2) / 2,
    )


def _centre_distance(left: DetectionCandidate, right: DetectionCandidate) -> float:
    left_centre = _centre(left)
    right_centre = _centre(right)
    return hypot(
        left_centre[0] - right_centre[0],
        left_centre[1] - right_centre[1],
    )


def _iou(left: DetectionCandidate, right: DetectionCandidate) -> float:
    intersection_width = max(0.0, min(left.x2, right.x2) - max(left.x1, right.x1))
    intersection_height = max(0.0, min(left.y2, right.y2) - max(left.y1, right.y1))
    intersection = intersection_width * intersection_height
    union = _area(left) + _area(right) - intersection
    return intersection / union if union > 0 else 0.0
