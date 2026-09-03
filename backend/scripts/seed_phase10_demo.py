from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.db.models import AccessibilityRoute, HazardObservation  # noqa: E402
from app.db.session import check_database, create_database_engine  # noqa: E402
from app.hazards.service import HazardService  # noqa: E402
from app.schemas.common import utc_now  # noqa: E402
from app.schemas.hazards import CreateHazardRequest  # noqa: E402


def main() -> int:
    settings = get_settings()
    engine = create_database_engine(settings.database_path)
    check_database(engine)
    seed_path = PROJECT_ROOT / "data" / "seed" / "phase10_hall_demo.json"
    payload = json.loads(seed_path.read_text(encoding="utf-8"))

    with Session(engine) as database:
        route = database.get(AccessibilityRoute, "hall-obstacle-course-v1")
        prior_count = int(
            database.scalar(
                select(func.count(HazardObservation.id)).where(
                    HazardObservation.session_id == payload["seed_id"]
                )
            )
            or 0
        )
    if route is None:
        raise RuntimeError("Phase 10 route is missing. Run Alembic upgrade head first.")
    if prior_count:
        print(f"Phase 10 demo data already exists ({prior_count} observations); no changes made.")
        engine.dispose()
        return 0

    service = HazardService(engine, settings.evidence_dir, settings)
    base_time = utc_now()
    created = 0
    merged = 0
    for report in payload["reports"]:
        for repeat_index in range(report["repeat"]):
            response = service.create(
                CreateHazardRequest.model_validate(
                    {
                        "session_id": payload["seed_id"],
                        "category": report["category"],
                        "severity": report["severity"],
                        "confidence": report["confidence"],
                        "risk_score": report["risk_score"],
                        "direction": "CENTRE",
                        "observed_at": base_time + timedelta(seconds=repeat_index),
                        "map_coordinate": {
                            "map_id": payload["map_id"],
                            "map_version": payload["map_version"],
                            "x": report["x"] + repeat_index * 0.004,
                            "y": report["y"] + repeat_index * 0.003,
                        },
                        "temporary": report["temporary"],
                        "evidence_consent": False,
                    }
                )
            )
            created += 1
            merged += int(response.merged_with_existing)

    result = service.accessibility()
    score = result.routes[0].score if result.routes else 100.0
    print(
        f"Seeded {created} observations ({merged} deterministic merges). "
        f"Hall score: {score}/100."
    )
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
