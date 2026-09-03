from __future__ import annotations

from app.risk.state_machine import StableDecision
from app.schemas.walk import GuidanceAction


def safety_preempts_target_guidance(decision: StableDecision) -> bool:
    """Any actionable mobility decision outranks optional target guidance."""

    return decision.action != GuidanceAction.CLEAR
