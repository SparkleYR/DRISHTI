from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


EXPECTED_MODELS = {
    "detector",
    "segmentation",
    "tracker",
    "depth",
    "india_hazards",
    "ocr",
    "vlm",
}


def test_health_reports_phase_eight_hall_readiness(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["status"] == "OK"
    assert payload["runtime_mode"] == "LOCAL_ONLY"
    assert payload["service"]["name"] == "drishti-backend"
    assert payload["compute"]["selected_device"] == "CUDA"
    assert payload["database"]["status"] == "READY"
    assert payload["walk_mode_available"] is True
    assert set(payload["models"]) == EXPECTED_MODELS
    assert payload["models"]["detector"]["status"] == "READY"
    assert payload["models"]["segmentation"]["status"] == "READY"
    assert payload["models"]["tracker"]["status"] == "READY"
    assert payload["models"]["depth"]["status"] == "DEGRADED"
    assert payload["models"]["india_hazards"]["status"] == "READY"
    assert "wall/dead-end" in payload["models"]["india_hazards"]["detail"]
    assert "free-space" in payload["models"]["india_hazards"]["detail"]
    assert payload["models"]["ocr"]["status"] == "READY"
    assert payload["models"]["vlm"]["status"] == "READY"
    assert all(
        model["status"] == "UNAVAILABLE"
        for name, model in payload["models"].items()
        if name
        not in {
            "detector",
            "segmentation",
            "tracker",
            "depth",
            "india_hazards",
            "ocr",
            "vlm",
        }
    )
    assert payload["server_time"].endswith("Z")
    datetime.fromisoformat(payload["server_time"].replace("Z", "+00:00"))


def test_openapi_exposes_only_approved_phase_ten_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/api/v1/health",
        "/api/v1/walk/sessions",
        "/api/v1/walk/sessions/{session_id}/end",
        "/api/v1/walk/analyze",
        "/api/v1/hazards",
        "/api/v1/hazards/nearby",
        "/api/v1/hazards/{hazard_id}/status",
        "/api/v1/hazards/{hazard_id}/merge",
            "/api/v1/dashboard/summary",
            "/api/v1/dashboard/accessibility",
        "/api/v1/explore",
        "/api/v1/vlm/query",
        "/api/v1/vlm/locate",
    }


def test_openapi_documents_the_phase_nine_vlm_contract(
    client: TestClient,
) -> None:
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/v1/vlm/query"]["post"]
    body_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_model_name = body_schema["$ref"].rsplit("/", 1)[-1]
    body_model = openapi["components"]["schemas"][body_model_name]

    assert set(body_model["required"]) == {"prompt"}
    assert set(body_model["properties"]) == {"frame", "image_base64", "prompt"}
    assert body_model["properties"]["prompt"]["maxLength"] == 500
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/VLMQueryResponse"
    }


def test_openapi_documents_the_frozen_multipart_contract(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/v1/walk/analyze"]["post"]
    body_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_model_name = body_schema["$ref"].rsplit("/", 1)[-1]
    body_model = openapi["components"]["schemas"][body_model_name]

    assert set(body_model["required"]) == {
        "frame",
        "session_id",
        "frame_id",
        "captured_at",
        "rotation_degrees",
    }
    assert body_model["properties"]["frame"] == {
        "type": "string",
        "contentMediaType": "application/octet-stream",
        "title": "Frame",
    }
    rotation_ref = body_model["properties"]["rotation_degrees"]["$ref"]
    rotation_name = rotation_ref.rsplit("/", 1)[-1]
    assert openapi["components"]["schemas"][rotation_name]["enum"] == [0, 90, 180, 270]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FrameAnalysisResponse"
    }


def test_openapi_documents_the_phase_seven_explore_contract(
    client: TestClient,
) -> None:
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/v1/explore"]["post"]
    body_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_model_name = body_schema["$ref"].rsplit("/", 1)[-1]
    body_model = openapi["components"]["schemas"][body_model_name]

    assert set(body_model["required"]) == {"frame", "mode"}
    assert body_model["properties"]["frame"] == {
        "type": "string",
        "contentMediaType": "application/octet-stream",
        "title": "Frame",
    }
    mode_ref = body_model["properties"]["mode"]["$ref"]
    mode_name = mode_ref.rsplit("/", 1)[-1]
    assert openapi["components"]["schemas"][mode_name]["enum"] == ["READ_TEXT"]
    assert body_model["properties"]["preferred_language"]["default"] == "en"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ReadTextResponse"
    }


def test_database_failure_returns_degraded_health(
    client: TestClient, monkeypatch
) -> None:
    def unavailable_database(_engine) -> None:
        raise OperationalError("SELECT 1", {}, Exception("offline"))

    monkeypatch.setattr("app.api.health.check_database", unavailable_database)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "DEGRADED"
    assert response.json()["database"]["status"] == "UNAVAILABLE"


def test_unknown_route_uses_stable_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/not-present")

    assert response.status_code == 404
    assert response.json()["schema_version"] == "1.0.0"
    assert response.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "The requested local resource was not found.",
        "retryable": False,
        "details": None,
    }


def test_dashboard_local_origin_is_allowed(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
