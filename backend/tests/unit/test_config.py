from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings


def test_defaults_are_local() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_path == PROJECT_ROOT / "data" / "drishti.db"
    assert settings.host == "0.0.0.0"
    assert all(origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1") for origin in settings.allowed_origins)


def test_model_paths_are_local_paths() -> None:
    settings = Settings(_env_file=None)

    for path in (
        settings.detector_model_path,
        settings.segmentation_model_path,
        settings.depth_model_path,
    ):
        assert isinstance(path, Path)
        assert str(path).startswith(str(PROJECT_ROOT))


def test_hysteresis_thresholds_must_not_overlap() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk_warn_enter=0.5, risk_warn_exit=0.5)


def test_risk_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk_weight_confidence=0.2)


def test_risk_thresholds_must_increase() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk_watch_enter=0.7)


def test_class_severities_must_be_normalized() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, risk_class_severities={"chair": 1.1})


def test_phase_eight_desk_severity_is_configured() -> None:
    assert Settings(_env_file=None).risk_class_severities["desk"] == 0.80


def test_indoor_segmentation_defaults_are_explicit() -> None:
    settings = Settings(_env_file=None)

    assert settings.segmentation_label_set == "ADE20K"
    assert settings.segmentation_model_path.name == "segformer-b0-ade20k"
    assert settings.surface_cost_road_weight == 0.0


def test_free_space_thresholds_must_increase() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            freespace_dead_end_max=0.4,
            freespace_side_open_min=0.3,
        )


def test_person_hazard_expiry_is_shorter_than_furniture_expiry() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            hazard_person_ttl_seconds=900,
            hazard_temporary_ttl_seconds=900,
        )


def test_proximity_thresholds_must_be_strictly_increasing() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            proximity_far_threshold=0.6,
            proximity_medium_threshold=0.5,
        )


def test_corridor_must_widen_toward_image_bottom() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            corridor_top_half_width=0.4,
            corridor_bottom_half_width=0.3,
        )


def test_wall_side_threshold_cannot_exceed_centre_threshold() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            wall_centre_ratio_threshold=0.2,
            wall_side_ratio_threshold=0.3,
        )
