from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from app.config import Settings
from app.risk.rules import ProposedDecision
from app.schemas.walk import CorridorChoice, GuidanceAction, RiskLevel


@dataclass(frozen=True)
class StableDecision:
    action: GuidanceAction
    level: RiskLevel
    reason_code: str
    preferred_corridor: CorridorChoice
    critical_track_ids: frozenset[int]
    speak: bool


class AlertStateMachine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._current = _clear_decision()
        self._pending: ProposedDecision | None = None
        self._pending_frames = 0
        self._clear_frames = 0
        self._last_spoken_at: datetime | None = None

    def apply(self, proposed: ProposedDecision, *, now: datetime) -> StableDecision:
        if proposed.level == RiskLevel.CRITICAL:
            self._reset_pending()
            self._clear_frames = 0
            return self._commit(proposed, now=now, bypass_cooldown=True)

        if proposed.action == GuidanceAction.PAUSE_UNCLEAR:
            self._reset_pending()
            self._clear_frames = 0
            return self._commit(proposed, now=now)

        if proposed.action == GuidanceAction.CLEAR:
            return self._apply_clear(proposed, now=now)

        self._clear_frames = 0
        if _same_decision(proposed, self._current):
            self._reset_pending()
            return self._commit(proposed, now=now)

        if self._pending is not None and _same_decision(proposed, self._pending):
            self._pending_frames += 1
        else:
            self._pending = proposed
            self._pending_frames = 1

        if self._pending_frames >= self._settings.alert_persistence_frames:
            self._reset_pending()
            return self._commit(proposed, now=now)

        if self._current.action in {
            GuidanceAction.MOVE_LEFT,
            GuidanceAction.MOVE_RIGHT,
        }:
            interim = ProposedDecision(
                action=GuidanceAction.PAUSE_UNCLEAR,
                level=RiskLevel.WARN,
                reason_code="DIRECTION_CHANGE_PENDING",
                preferred_corridor=CorridorChoice.NONE,
            )
            return self._commit(interim, now=now)
        return _stable(
            ProposedDecision(
                action=GuidanceAction.CLEAR,
                level=RiskLevel.WATCH,
                reason_code="ALERT_PERSISTENCE_PENDING",
                preferred_corridor=CorridorChoice.NONE,
            ),
            speak=False,
        )

    def _apply_clear(
        self,
        proposed: ProposedDecision,
        *,
        now: datetime,
    ) -> StableDecision:
        self._reset_pending()
        if self._current.action == GuidanceAction.CLEAR:
            self._clear_frames = 0
            return self._commit(proposed, now=now)
        if proposed.evidence_score >= self._settings.risk_warn_exit:
            self._clear_frames = 0
            return _stable(
                ProposedDecision(
                    action=GuidanceAction.CAUTION,
                    level=RiskLevel.WATCH,
                    reason_code="RISK_HYSTERESIS_ACTIVE",
                    preferred_corridor=CorridorChoice.CENTRE,
                    evidence_score=proposed.evidence_score,
                ),
                speak=False,
            )
        self._clear_frames += 1
        if self._clear_frames >= self._settings.alert_clear_frames:
            self._clear_frames = 0
            return self._commit(proposed, now=now)
        return _stable(
            ProposedDecision(
                action=GuidanceAction.CAUTION,
                level=RiskLevel.WATCH,
                reason_code="RISK_DECAY_PENDING",
                preferred_corridor=CorridorChoice.CENTRE,
            ),
            speak=False,
        )

    def _commit(
        self,
        proposed: ProposedDecision,
        *,
        now: datetime,
        bypass_cooldown: bool = False,
    ) -> StableDecision:
        changed = not _same_decision(proposed, self._current)
        increased = _level_rank(proposed.level) > _level_rank(self._current.level)
        cooldown_elapsed = (
            self._last_spoken_at is None
            or (now - self._last_spoken_at).total_seconds()
            >= self._settings.alert_cooldown_seconds
        )
        has_message = proposed.action != GuidanceAction.CLEAR
        speak = has_message and (
            changed or increased or (cooldown_elapsed and not bypass_cooldown)
        )
        if bypass_cooldown and (changed or increased):
            speak = True
        self._current = proposed
        if speak:
            self._last_spoken_at = now
        return _stable(proposed, speak=speak)

    def _reset_pending(self) -> None:
        self._pending = None
        self._pending_frames = 0


class RiskSessionStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: dict[str, AlertStateMachine] = {}
        self._lock = Lock()

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = AlertStateMachine(self._settings)

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def apply(
        self,
        session_id: str,
        proposed: ProposedDecision,
        *,
        now: datetime,
    ) -> StableDecision:
        with self._lock:
            machine = self._sessions.setdefault(
                session_id,
                AlertStateMachine(self._settings),
            )
            return machine.apply(proposed, now=now)


def _clear_decision() -> ProposedDecision:
    return ProposedDecision(
        action=GuidanceAction.CLEAR,
        level=RiskLevel.CLEAR,
        reason_code="PATH_CLEAR",
        preferred_corridor=CorridorChoice.CENTRE,
    )


def _same_decision(left: ProposedDecision, right: ProposedDecision) -> bool:
    return (
        left.action == right.action
        and left.level == right.level
        and left.preferred_corridor == right.preferred_corridor
        and left.reason_code == right.reason_code
    )


def _stable(decision: ProposedDecision, *, speak: bool) -> StableDecision:
    return StableDecision(
        action=decision.action,
        level=decision.level,
        reason_code=decision.reason_code,
        preferred_corridor=decision.preferred_corridor,
        critical_track_ids=decision.critical_track_ids,
        speak=speak,
    )


def _level_rank(level: RiskLevel) -> int:
    return {
        RiskLevel.CLEAR: 0,
        RiskLevel.WATCH: 1,
        RiskLevel.WARN: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }[level]
