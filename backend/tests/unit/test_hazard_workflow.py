from app.hazards.service import ALLOWED_TRANSITIONS
from app.schemas.hazards import HazardStatus


def test_hazard_transition_matrix_matches_frozen_contract() -> None:
    assert ALLOWED_TRANSITIONS == {
        HazardStatus.NEW: frozenset(
            {HazardStatus.VERIFIED, HazardStatus.REJECTED}
        ),
        HazardStatus.VERIFIED: frozenset(
            {
                HazardStatus.ASSIGNED,
                HazardStatus.RESOLVED,
                HazardStatus.REJECTED,
            }
        ),
        HazardStatus.ASSIGNED: frozenset(
            {HazardStatus.IN_PROGRESS, HazardStatus.RESOLVED}
        ),
        HazardStatus.IN_PROGRESS: frozenset({HazardStatus.RESOLVED}),
        HazardStatus.RESOLVED: frozenset(),
        HazardStatus.REJECTED: frozenset(),
    }
