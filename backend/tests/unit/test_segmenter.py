from pathlib import Path

from app.config import Settings
from app.perception.segmenter import load_segmenter


def test_safetensors_checkpoint_passes_local_file_validation(tmp_path: Path) -> None:
    model_path = tmp_path / "segformer"
    model_path.mkdir()
    for filename in ("config.json", "preprocessor_config.json", "model.safetensors"):
        (model_path / filename).write_text("{}", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        models_dir=tmp_path,
        segmentation_model_path=model_path,
        compute_device="NONE",
    )

    segmenter = load_segmenter(settings)

    assert segmenter.detail == "No segmentation inference device is configured."


def test_checkpoint_without_supported_weights_is_rejected(tmp_path: Path) -> None:
    model_path = tmp_path / "segformer"
    model_path.mkdir()
    for filename in ("config.json", "preprocessor_config.json"):
        (model_path / filename).write_text("{}", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        models_dir=tmp_path,
        segmentation_model_path=model_path,
        compute_device="NONE",
    )

    segmenter = load_segmenter(settings)

    assert "incomplete" in segmenter.detail
