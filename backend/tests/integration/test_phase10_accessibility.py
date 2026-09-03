from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import AccessibilityRoute, AccessibilitySegment, Hazard, HazardObservation, HazardStatusHistory
from app.schemas.common import utc_now


NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _install_route(client: TestClient) -> None:
    with Session(client.app.state.database_engine) as database:
        with database.begin():
            database.add(
                AccessibilityRoute(
                    id="phase10-route-v1",
                    route_key="phase10-route",
                    name="Hall Obstacle Course",
                    description="Controlled judging route",
                    map_id="phase10-hall",
                    map_version="1",
                    specification_version="1.0.0",
                    active=True,
                )
            )
            database.add(
                AccessibilitySegment(
                    id="phase10-main",
                    route_id="phase10-route-v1",
                    segment_key="main",
                    name="Main aisle",
                    sequence=1,
                    start_x=0.5,
                    start_y=0.9,
                    end_x=0.5,
                    end_y=0.1,
                    corridor_radius=0.15,
                )
            )


def _report(client: TestClient, *, category: str = "chair", x: float = 0.5, map_version: str = "1", observed_at: datetime = NOW, temporary: bool = False) -> dict:
    response = client.post(
        "/api/v1/hazards",
        json={
            "category": category,
            "severity": "HIGH",
            "confidence": 0.9,
            "risk_score": 0.8,
            "direction": "CENTRE",
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "map_coordinate": {
                "map_id": "phase10-hall",
                "map_version": map_version,
                "x": x,
                "y": 0.5,
            },
            "temporary": temporary,
            "evidence_consent": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_nearest_eligible_duplicate_merges_and_preserves_observations(client: TestClient) -> None:
    older = _report(client, category="chair obstruction", x=0.46)
    separate = _report(client, category="chair", x=0.54)
    merged = _report(client, category="chair", x=0.49, observed_at=NOW + timedelta(seconds=30))

    assert older["hazard"]["id"] != separate["hazard"]["id"]
    assert merged["merged_with_existing"] is True
    assert merged["hazard"]["id"] == older["hazard"]["id"]
    assert merged["hazard"]["confirmation_count"] == 2
    with Session(client.app.state.database_engine) as database:
        observations = list(
            database.scalars(
                select(HazardObservation).where(
                    HazardObservation.hazard_id == older["hazard"]["id"]
                )
            )
        )
    assert len(observations) == 2
    assert len({item.source_hazard_id for item in observations}) == 2


def test_exact_duplicate_tie_breaks_by_first_seen_then_id(client: TestClient) -> None:
    with Session(client.app.state.database_engine) as database:
        with database.begin():
            for hazard_id, x in [("a-hazard", 0.46875), ("b-hazard", 0.53125)]:
                database.add(
                    Hazard(
                        id=hazard_id,
                        category="chair",
                        severity="HIGH",
                        status="NEW",
                        map_id="phase10-hall",
                        map_version="1",
                        map_x=x,
                        map_y=0.5,
                        latitude=None,
                        longitude=None,
                        accuracy_m=None,
                        first_seen_at=NOW,
                        last_seen_at=NOW,
                        confidence=0.8,
                        confirmation_count=1,
                        temporary=False,
                        assigned_to=None,
                        version=1,
                        evidence_path=None,
                        merged_into_id=None,
                    )
                )
    merged = _report(client, category="chair", x=0.5, observed_at=NOW + timedelta(seconds=1))
    assert merged["merged_with_existing"] is True
    assert merged["hazard"]["id"] == "a-hazard"


def test_different_category_map_version_and_distance_do_not_merge(client: TestClient) -> None:
    original = _report(client, category="chair", x=0.2)
    other_category = _report(client, category="bag", x=0.2)
    other_version = _report(client, category="chair", x=0.2, map_version="2")
    distant = _report(client, category="chair", x=0.8)

    ids = {item["hazard"]["id"] for item in [original, other_category, other_version, distant]}
    assert len(ids) == 4
    assert all(not item["merged_with_existing"] for item in [original, other_category, other_version, distant])


def test_person_expires_before_movable_furniture_and_records_history(client: TestClient, settings) -> None:
    reference_time = utc_now()
    observed = reference_time - timedelta(seconds=settings.hazard_person_ttl_seconds + 1)
    person = _report(client, category="person", x=0.3, observed_at=observed, temporary=True)
    chair = _report(client, category="chair", x=0.7, observed_at=observed, temporary=True)

    expired = client.app.state.hazard_service.expire_temporary(now=reference_time)
    assert expired == 1
    active = client.get("/api/v1/hazards", params={"active": "true"}).json()["items"]
    assert [item["id"] for item in active] == [chair["hazard"]["id"]]
    with Session(client.app.state.database_engine) as database:
        row = database.get(Hazard, person["hazard"]["id"])
        history = list(
            database.scalars(
                select(HazardStatusHistory).where(
                    HazardStatusHistory.hazard_id == person["hazard"]["id"]
                )
            )
        )
    assert row is not None and row.status == "RESOLVED"
    assert history[0].operator_alias == "system-expiry"
    assert "expired without reconfirmation" in (history[0].note or "")


def test_accessibility_is_explainable_and_resolution_restores_score(client: TestClient) -> None:
    _install_route(client)
    first = _report(client, category="chair obstruction", x=0.5)
    recurring = _report(client, category="chair", x=0.51, observed_at=NOW + timedelta(seconds=5))
    hazard = recurring["hazard"]
    verified_response = client.patch(
        f"/api/v1/hazards/{hazard['id']}/status",
        json={
            "expected_version": hazard["version"],
            "expected_status": "NEW",
            "new_status": "VERIFIED",
            "operator_alias": "judge-demo",
        },
    )
    assert verified_response.status_code == 200, verified_response.text
    verified = verified_response.json()["hazard"]

    response = client.get("/api/v1/dashboard/accessibility")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["advisory_only"] is True
    assert "not live navigation" in body["disclaimer"]
    route = body["routes"][0]
    assert route["score"] < 100
    assert route["active_hazard_count"] == 1
    assert route["recurring_hazard_count"] == 1
    factor = route["segments"][0]["factors"][0]
    assert factor["confirmation_count"] == 2
    assert set(factor) >= {
        "severity_points", "status_factor", "recurrence_factor",
        "confidence_factor", "freshness_factor", "spatial_factor",
        "penalty_points", "explanation",
    }

    resolved = client.patch(
        f"/api/v1/hazards/{verified['id']}/status",
        json={
            "expected_version": verified["version"],
            "expected_status": "VERIFIED",
            "new_status": "RESOLVED",
            "operator_alias": "judge-demo",
            "note": "Chair removed from demo aisle",
        },
    )
    assert resolved.status_code == 200
    restored = client.get("/api/v1/dashboard/accessibility").json()["routes"][0]
    assert restored["score"] == 100
    assert restored["active_hazard_count"] == 0
    assert first["hazard"]["id"] == recurring["hazard"]["id"]


def test_analytics_database_failure_does_not_disable_walk_mode(client: TestClient) -> None:
    with client.app.state.database_engine.begin() as connection:
        connection.execute(text("DROP TABLE accessibility_routes"))

    failed = client.get("/api/v1/dashboard/accessibility")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    walk = client.post(
        "/api/v1/walk/sessions", json={"device_alias": "phase10-db-failure"}
    )
    assert walk.status_code == 201
