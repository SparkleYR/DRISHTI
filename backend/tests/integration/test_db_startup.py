from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings


def test_backend_startup_creates_local_sqlite_file(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert settings.database_path.exists()
    assert settings.database_path.is_file()
    assert settings.database_path.parent.name == "data"


def test_backend_startup_creates_only_local_runtime_paths(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    client.get("/api/v1/health")

    created_files = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}
    assert created_files <= {"data/drishti.db", "logs/drishti.log"}
