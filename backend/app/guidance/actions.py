from __future__ import annotations

from app.risk.state_machine import StableDecision
from app.schemas.walk import GuidanceAction, GuidanceContract, HapticPattern


_SPEECH = {
    GuidanceAction.CLEAR: "",
    GuidanceAction.CAUTION: "Obstacle nearby.",
    GuidanceAction.MOVE_LEFT: "Path blocked. Move slightly left.",
    GuidanceAction.MOVE_RIGHT: "Path blocked. Move slightly right.",
    GuidanceAction.STOP: "Stop. Obstacle directly ahead.",
    GuidanceAction.PAUSE_UNCLEAR: "Path unclear. Please pause.",
}

_HAPTICS = {
    GuidanceAction.CLEAR: HapticPattern.NONE,
    GuidanceAction.CAUTION: HapticPattern.CAUTION_SHORT,
    GuidanceAction.MOVE_LEFT: HapticPattern.WARNING_DOUBLE,
    GuidanceAction.MOVE_RIGHT: HapticPattern.WARNING_DOUBLE,
    GuidanceAction.STOP: HapticPattern.CRITICAL_RAPID,
    GuidanceAction.PAUSE_UNCLEAR: HapticPattern.UNCLEAR_LONG,
}


def build_guidance(
    decision: StableDecision,
    *,
    haptics_enabled: bool,
) -> GuidanceContract:
    speech = _SPEECH[decision.action]
    return GuidanceContract(
        level=decision.level,
        action=decision.action,
        speech=speech,
        haptic_pattern=(
            _HAPTICS[decision.action] if haptics_enabled else HapticPattern.NONE
        ),
        speak=decision.speak and bool(speech),
        reason_code=decision.reason_code,
    )
