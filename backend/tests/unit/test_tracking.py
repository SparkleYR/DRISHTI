from datetime import UTC, datetime, timedelta

from app.perception.detector import DetectionCandidate
from app.perception.tracking import SessionTracker, TrackingSessionStore


def detection(
    *,
    label: str = "person",
    x1: float = 0.4,
    y1: float = 0.4,
    x2: float = 0.6,
    y2: float = 0.9,
) -> DetectionCandidate:
    return DetectionCandidate(label, 0.9, x1, y1, x2, y2)


def test_nearby_frames_keep_track_id_and_report_motion_and_growth() -> None:
    tracker = SessionTracker(
        iou_threshold=0.2,
        centre_distance_threshold=0.12,
        max_age_frames=3,
    )
    now = datetime.now(UTC)
    first = tracker.update([detection()], frame_id=0, captured_at=now)[0]
    second = tracker.update(
        [detection(x1=0.37, y1=0.35, x2=0.63, y2=0.92)],
        frame_id=1,
        captured_at=now + timedelta(milliseconds=500),
    )[0]

    assert first.track_id == second.track_id == 1
    assert second.area_change is not None and second.area_change > 0
    assert second.approach_rate is not None and second.approach_rate > 0
    assert second.motion_dy is not None and second.motion_dy < 0


def test_different_labels_do_not_share_a_track() -> None:
    tracker = SessionTracker(
        iou_threshold=0.2,
        centre_distance_threshold=0.12,
        max_age_frames=3,
    )
    now = datetime.now(UTC)
    person = tracker.update([detection(label="person")], frame_id=0, captured_at=now)[0]
    chair = tracker.update([detection(label="chair")], frame_id=1, captured_at=now)[0]
    assert person.track_id != chair.track_id


def test_tracking_state_is_scoped_and_removed_by_session() -> None:
    store = TrackingSessionStore(
        iou_threshold=0.2,
        centre_distance_threshold=0.12,
        max_age_frames=3,
    )
    now = datetime.now(UTC)
    store.start_session("a")
    store.start_session("b")
    assert store.update("a", [detection()], frame_id=0, captured_at=now)[0].track_id == 1
    assert store.update("b", [detection()], frame_id=0, captured_at=now)[0].track_id == 1
    store.end_session("a")
    assert store.update("a", [detection()], frame_id=1, captured_at=now)[0].track_id == 1
