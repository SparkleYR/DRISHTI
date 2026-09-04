from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock

from app.schemas.walk import DetectionResult


NormalizedBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Landmark:
    label: str
    world_bearing_deg: float | None
    last_center_x: float
    last_box_h: float
    last_box_bottom: float
    last_box: NormalizedBox
    first_seen_ms: int
    last_seen_ms: int
    sightings: int


class LandmarkMemoryStore:
    """TTL-bounded, process-local landmark observations scoped to Walk sessions."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        camera_hfov_degrees: float,
        allow_person: bool = False,
        bearing_gate_degrees: float = 25.0,
    ) -> None:
        self._ttl_ms = ttl_seconds * 1000
        self._max_entries = max_entries
        self._hfov = camera_hfov_degrees
        self._allow_person = allow_person
        self._bearing_gate = bearing_gate_degrees
        self._sessions: dict[str, list[Landmark]] = {}
        self._lock = RLock()

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = []

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def observe(
        self,
        session_id: str,
        *,
        now_ms: int,
        heading_degrees: float | None,
        detections: list[DetectionResult],
    ) -> None:
        with self._lock:
            entries = self._sessions.setdefault(session_id, [])
            self._expire(entries, now_ms)
            for detection in detections:
                if detection.label.lower() == "person" and not self._allow_person:
                    continue
                box = (
                    detection.bbox.x1,
                    detection.bbox.y1,
                    detection.bbox.x2,
                    detection.bbox.y2,
                )
                self._remember(entries, detection.label, now_ms, heading_degrees, box)
            self._trim(entries)

    def remember(
        self,
        session_id: str,
        *,
        label: str,
        now_ms: int,
        heading_degrees: float | None,
        box: NormalizedBox,
    ) -> Landmark:
        with self._lock:
            entries = self._sessions.setdefault(session_id, [])
            self._expire(entries, now_ms)
            result = self._remember(entries, label, now_ms, heading_degrees, box)
            self._trim(entries)
            return replace(result)

    def resolve(self, session_id: str, target_name: str, *, now_ms: int) -> Landmark | None:
        target = normalize_label(target_name)
        with self._lock:
            entries = self._sessions.setdefault(session_id, [])
            self._expire(entries, now_ms)
            matches = [entry for entry in entries if labels_match(target, entry.label)]
            if not matches:
                return None
            return replace(max(matches, key=lambda item: item.last_seen_ms))

    def count(self, session_id: str, *, now_ms: int) -> int:
        with self._lock:
            entries = self._sessions.get(session_id, [])
            self._expire(entries, now_ms)
            return len(entries)

    def _remember(
        self,
        entries: list[Landmark],
        label: str,
        now_ms: int,
        heading_degrees: float | None,
        box: NormalizedBox,
    ) -> Landmark:
        canonical = normalize_label(label)
        center_x = (box[0] + box[2]) / 2.0
        world_bearing = (
            wrap180(heading_degrees + (center_x - 0.5) * self._hfov)
            if heading_degrees is not None
            else None
        )
        same_label = [
            (index, item)
            for index, item in enumerate(entries)
            if normalize_label(item.label) == canonical
        ]
        candidate: tuple[int, Landmark] | None = None
        if world_bearing is not None:
            gated = [
                pair
                for pair in same_label
                if pair[1].world_bearing_deg is not None
                and abs(wrap180(world_bearing - pair[1].world_bearing_deg))
                <= self._bearing_gate
            ]
            if gated:
                candidate = min(
                    gated,
                    key=lambda pair: abs(
                        wrap180(world_bearing - (pair[1].world_bearing_deg or 0.0))
                    ),
                )
        elif same_label:
            candidate = max(same_label, key=lambda pair: pair[1].last_seen_ms)

        if candidate is None:
            landmark = Landmark(
                label=canonical,
                world_bearing_deg=world_bearing,
                last_center_x=center_x,
                last_box_h=box[3] - box[1],
                last_box_bottom=box[3],
                last_box=box,
                first_seen_ms=now_ms,
                last_seen_ms=now_ms,
                sightings=1,
            )
            entries.append(landmark)
            return landmark

        index, previous = candidate
        landmark = Landmark(
            label=previous.label,
            world_bearing_deg=world_bearing,
            last_center_x=center_x,
            last_box_h=box[3] - box[1],
            last_box_bottom=box[3],
            last_box=box,
            first_seen_ms=previous.first_seen_ms,
            last_seen_ms=now_ms,
            sightings=previous.sightings + 1,
        )
        entries[index] = landmark
        return landmark

    def _expire(self, entries: list[Landmark], now_ms: int) -> None:
        entries[:] = [item for item in entries if now_ms - item.last_seen_ms <= self._ttl_ms]

    def _trim(self, entries: list[Landmark]) -> None:
        if len(entries) > self._max_entries:
            entries.sort(key=lambda item: item.last_seen_ms, reverse=True)
            del entries[self._max_entries :]


def normalize_label(value: str) -> str:
    normalized = " ".join(value.lower().strip().split())
    for article in ("a ", "an ", "the "):
        if normalized.startswith(article):
            return normalized[len(article) :]
    return normalized


_SYNONYMS = {
    "sofa": "couch",
    "fridge": "refrigerator",
    "tv": "television",
    "plant": "potted plant",
}


def labels_match(target: str, observed: str) -> bool:
    left = normalize_label(target)
    right = normalize_label(observed)
    if left == right:
        return True
    left = _SYNONYMS.get(left, left)
    right = _SYNONYMS.get(right, right)
    if left == right:
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    return bool(left_tokens and right_tokens) and (
        left_tokens <= right_tokens or right_tokens <= left_tokens
    )


def wrap180(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0
