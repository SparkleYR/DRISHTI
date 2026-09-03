from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Hazard, HazardObservation, HazardStatusHistory


NOW = datetime.now(UTC).isoformat().replace("+00:00", "Z")


def report_payload(**overrides) -> dict:
    payload = {
        "category": "chair obstruction",
        "severity": "HIGH",
        "confidence": 0.88,
        "risk_score": 0.82,
        "direction": "CENTRE",
        "observed_at": NOW,
        "map_coordinate": {
            "map_id": "phase6-test-map",
            "map_version": "1",
            "x": 0.5,
            "y": 0.5,
        },
        "temporary": True,
        "evidence_consent": False,
    }
    payload.update(overrides)
    return payload


def create_report(client: TestClient, **overrides) -> dict:
    response = client.post("/api/v1/hazards", json=report_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["hazard"]


def transition(
    client: TestClient,
    hazard: dict,
    new_status: str,
    **overrides,
) -> dict:
    payload = {
        "expected_version": hazard["version"],
        "expected_status": hazard["status"],
        "new_status": new_status,
        "operator_alias": "access-desk",
    }
    payload.update(overrides)
    response = client.patch(
        f"/api/v1/hazards/{hazard['id']}/status", json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()["hazard"]


def test_anonymous_report_lists_and_filters_by_nearby_map(client: TestClient) -> None:
    hazard = create_report(client)

    assert hazard["status"] == "NEW"
    assert hazard["version"] == 1
    assert hazard["confirmation_count"] == 1
    assert hazard["has_consented_evidence"] is False
    assert "user" not in json.dumps(hazard).lower()

    active = client.get("/api/v1/hazards", params={"active": "true"})
    assert active.status_code == 200
    assert [item["id"] for item in active.json()["items"]] == [hazard["id"]]

    nearby = client.get(
        "/api/v1/hazards/nearby",
        params={
            "map_id": "phase6-test-map",
            "map_version": "1",
            "map_x": 0.52,
            "map_y": 0.48,
            "radius": 0.1,
        },
    )
    assert nearby.status_code == 200
    assert [item["id"] for item in nearby.json()["items"]] == [hazard["id"]]


def test_full_status_workflow_records_history_and_suppresses_resolution(
    client: TestClient, settings: Settings
) -> None:
    hazard = create_report(client)
    hazard = transition(client, hazard, "VERIFIED")
    hazard = transition(client, hazard, "ASSIGNED", assigned_to="facilities-team")
    assert hazard["assigned_to"] == "facilities-team"
    hazard = transition(client, hazard, "IN_PROGRESS")
    hazard = transition(client, hazard, "RESOLVED", note="Chair removed")

    assert hazard["status"] == "RESOLVED"
    assert hazard["version"] == 5
    assert client.get("/api/v1/hazards", params={"active": "true"}).json()[
        "items"
    ] == []
    assert client.get(
        "/api/v1/hazards/nearby",
        params={
            "map_id": "phase6-test-map",
            "map_version": "1",
            "map_x": 0.5,
            "map_y": 0.5,
            "radius": 0.2,
        },
    ).json()["items"] == []

    with Session(client.app.state.database_engine) as database:
        history = list(
            database.scalars(
                select(HazardStatusHistory)
                .where(HazardStatusHistory.hazard_id == hazard["id"])
                .order_by(HazardStatusHistory.changed_at)
            )
        )
    assert [(item.from_status, item.to_status) for item in history] == [
        ("NEW", "VERIFIED"),
        ("VERIFIED", "ASSIGNED"),
        ("ASSIGNED", "IN_PROGRESS"),
        ("IN_PROGRESS", "RESOLVED"),
    ]
    assert all(item.operator_alias == "access-desk" for item in history)

    summary = client.get("/api/v1/dashboard/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["counts"]["resolved"] == 1
    assert body["active_verified_hazards"] == 0
    assert body["recently_resolved"][0]["id"] == hazard["id"]
    assert body["median_resolution_minutes"] is not None


def test_invalid_and_stale_transitions_are_rejected(client: TestClient) -> None:
    hazard = create_report(client)
    invalid = client.patch(
        f"/api/v1/hazards/{hazard['id']}/status",
        json={
            "expected_version": 1,
            "expected_status": "NEW",
            "new_status": "RESOLVED",
            "operator_alias": "desk",
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    updated = transition(client, hazard, "VERIFIED")
    stale = client.patch(
        f"/api/v1/hazards/{hazard['id']}/status",
        json={
            "expected_version": 1,
            "expected_status": "NEW",
            "new_status": "REJECTED",
            "operator_alias": "desk",
        },
    )
    assert updated["version"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"
    assert stale.json()["error"]["retryable"] is True


def test_evidence_requires_consent_and_is_stored_only_locally(
    client: TestClient, settings: Settings
) -> None:
    image = np.zeros((20, 20, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    jpeg = encoded.tobytes()

    rejected = client.post(
        "/api/v1/hazards",
        data={"payload": json.dumps(report_payload())},
        files={"evidence": ("evidence.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_REQUEST"
    assert not settings.evidence_dir.exists()

    consented_payload = report_payload(evidence_consent=True)
    accepted = client.post(
        "/api/v1/hazards",
        data={"payload": json.dumps(consented_payload)},
        files={"evidence": ("evidence.jpg", io.BytesIO(jpeg), "image/jpeg")},
    )
    assert accepted.status_code == 201, accepted.text
    hazard = accepted.json()["hazard"]
    assert hazard["has_consented_evidence"] is True
    stored = list(settings.evidence_dir.glob("*.jpg"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == jpeg


def test_operator_merge_preserves_observation_provenance(
    client: TestClient,
) -> None:
    primary = create_report(
        client,
        category="blocked walkway",
        confidence=0.7,
        map_coordinate={
            "map_id": "phase6-test-map",
            "map_version": "1",
            "x": 0.2,
            "y": 0.5,
        },
    )
    duplicate = create_report(
        client,
        category="blocked walkway",
        confidence=0.9,
        observed_at="2026-09-03T12:02:00Z",
        map_coordinate={
            "map_id": "phase6-test-map",
            "map_version": "1",
            "x": 0.8,
            "y": 0.5,
        },
    )
    response = client.post(
        f"/api/v1/hazards/{primary['id']}/merge",
        json={
            "duplicate_hazard_id": duplicate["id"],
            "expected_primary_version": primary["version"],
            "expected_duplicate_version": duplicate["version"],
            "operator_alias": "access-desk",
            "note": "Same obstruction",
        },
    )
    assert response.status_code == 200, response.text
    merged = response.json()["primary_hazard"]
    assert merged["confirmation_count"] == 2
    assert merged["confidence"] == 0.9
    assert merged["version"] == 2

    with Session(client.app.state.database_engine) as database:
        observations = list(
            database.scalars(
                select(HazardObservation).where(
                    HazardObservation.hazard_id == primary["id"]
                )
            )
        )
        duplicate_row = database.get(Hazard, duplicate["id"])
        merge_history = list(
            database.scalars(
                select(HazardStatusHistory).where(
                    HazardStatusHistory.hazard_id == duplicate["id"]
                )
            )
        )
    assert len(observations) == 2
    assert {item.source_hazard_id for item in observations} == {
        primary["id"],
        duplicate["id"],
    }
    assert duplicate_row is not None
    assert duplicate_row.merged_into_id == primary["id"]
    assert len(merge_history) == 1
    assert merge_history[0].operator_alias == "access-desk"


def test_hazard_database_failure_does_not_break_walk_sessions(
    client: TestClient,
) -> None:
    with client.app.state.database_engine.begin() as connection:
        connection.execute(text("DROP TABLE hazards"))

    failed = client.get("/api/v1/hazards")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    health = client.get("/api/v1/health")
    assert health.json()["status"] == "DEGRADED"
    assert health.json()["database"]["status"] == "UNAVAILABLE"

    walk = client.post(
        "/api/v1/walk/sessions", json={"device_alias": "phase6-failure-test"}
    )
    assert walk.status_code == 201


def test_filters_pagination_and_nearby_validation(client: TestClient) -> None:
    create_report(client, category="first")
    create_report(client, category="second")
    first_page = client.get("/api/v1/hazards", params={"limit": 1})
    assert first_page.status_code == 200
    cursor = first_page.json()["next_cursor"]
    assert cursor
    second_page = client.get(
        "/api/v1/hazards", params={"limit": 1, "cursor": cursor}
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["id"] != first_page.json()["items"][0]["id"]

    mixed = client.get(
        "/api/v1/hazards/nearby",
        params={
            "map_id": "map",
            "map_version": "1",
            "map_x": 0.5,
            "map_y": 0.5,
            "radius": 0.2,
            "latitude": 10,
            "longitude": 20,
            "radius_m": 10,
        },
    )
    assert mixed.status_code == 422
    assert mixed.json()["error"]["code"] == "INVALID_REQUEST"

    conflicting_filters = client.get(
        "/api/v1/hazards", params=[("active", "true"), ("status", "NEW")]
    )
    assert conflicting_filters.status_code == 422


def test_openapi_documents_both_hazard_report_content_types(
    client: TestClient,
) -> None:
    operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/hazards"
    ]["post"]
    content = operation["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}
    assert content["application/json"]["schema"]["title"] == "CreateHazardRequest"
    assert "$ref" not in json.dumps(content["application/json"]["schema"])
    assert content["multipart/form-data"]["schema"]["properties"]["evidence"] == {
        "type": "string",
        "format": "binary",
    }
