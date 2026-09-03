from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="DRISHTI_",
        extra="ignore",
    )

    service_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: Path = PROJECT_ROOT / "logs" / "drishti.log"
    allowed_origins: list[str] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]

    database_path: Path = PROJECT_ROOT / "data" / "drishti.db"
    evidence_dir: Path = PROJECT_ROOT / "data" / "evidence"
    max_evidence_image_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    hazard_duplicate_radius: float = Field(default=0.05, gt=0.0, le=0.25)
    hazard_duplicate_window_seconds: int = Field(default=15 * 60, ge=1, le=86_400)
    hazard_temporary_ttl_seconds: int = Field(default=15 * 60, ge=1, le=86_400)
    hazard_person_ttl_seconds: int = Field(default=45, ge=1, le=3_600)
    tesseract_command: str = str(
        PROJECT_ROOT / ".tools" / "Tesseract-OCR" / "tesseract.exe"
    )
    ocr_language: Literal["eng"] = "eng"
    ocr_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    explore_max_image_width: int = Field(default=2048, ge=320, le=4096)
    explore_max_image_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    explore_max_image_pixels: int = Field(default=8_388_608, ge=1024)
    vlm_model_path: Path = PROJECT_ROOT / "models" / "vlm" / "moondream2"
    vlm_tokenizer_path: Path = (
        PROJECT_ROOT / "models" / "vlm" / "starmie-v1" / "tokenizer.json"
    )
    vlm_modules_cache: Path = (
        PROJECT_ROOT / ".cache" / "huggingface" / "modules"
    )
    vlm_timeout_seconds: float = Field(default=45.0, ge=1.0, le=180.0)
    vlm_min_free_vram_mb: int = Field(default=4600, ge=1024, le=16_384)
    vlm_max_new_tokens: int = Field(default=128, ge=16, le=512)
    vlm_max_image_width: int = Field(default=1280, ge=320, le=4096)
    vlm_max_image_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    vlm_max_image_pixels: int = Field(default=8_388_608, ge=1024)
    compute_device: Literal["CUDA", "CPU", "NONE"] = "CUDA"
    compute_device_name: str | None = "NVIDIA GeForce RTX 4060 Laptop GPU"

    models_dir: Path = PROJECT_ROOT / "models"
    detector_model_path: Path = PROJECT_ROOT / "models" / "detector" / "yolo11n.pt"
    detector_confidence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    detector_image_size: int = Field(default=640, ge=320, le=1280, multiple_of=32)
    segmentation_model_path: Path = (
        PROJECT_ROOT / "models" / "segmentation" / "segformer-b0-cityscapes"
    )
    segmentation_input_height: int = Field(default=512, ge=256, le=1024, multiple_of=32)
    segmentation_input_width: int = Field(default=1024, ge=256, le=2048, multiple_of=32)
    depth_model_path: Path = PROJECT_ROOT / "models" / "depth" / "model.pt"

    track_iou_threshold: float = Field(default=0.20, ge=0.0, le=1.0)
    track_centre_distance_threshold: float = Field(default=0.12, gt=0.0, le=1.0)
    track_max_age_frames: int = Field(default=3, ge=1, le=30)
    approach_change_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    proximity_area_weight: float = Field(default=0.55, ge=0.0, le=1.0)
    proximity_area_scale: float = Field(default=0.50, gt=0.0, le=1.0)
    proximity_far_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    proximity_medium_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    proximity_near_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    corridor_horizon_y: float = Field(default=0.38, ge=0.1, le=0.8)
    corridor_top_half_width: float = Field(default=0.08, gt=0.0, le=0.45)
    corridor_bottom_half_width: float = Field(default=0.42, gt=0.1, le=0.5)
    corridor_clear_margin: float = Field(default=0.10, ge=0.0, le=1.0)
    wall_min_pixel_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    wall_centre_ratio_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    wall_side_ratio_threshold: float = Field(default=0.20, ge=0.0, le=1.0)

    recommended_capture_fps: float = Field(default=2.0, gt=0, le=5)
    max_image_width: int = Field(default=1280, ge=320, le=4096)
    max_image_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    max_image_pixels: int = Field(default=4_194_304, ge=1024)
    max_multipart_overhead_bytes: int = Field(default=256 * 1024, ge=1024)
    max_result_age_ms: int = Field(default=3000, ge=100, le=10000)
    risk_watch_enter: float = Field(default=0.25, ge=0, le=1)
    risk_warn_enter: float = Field(default=0.65, ge=0, le=1)
    risk_warn_exit: float = Field(default=0.50, ge=0, le=1)
    risk_high_enter: float = Field(default=0.80, ge=0, le=1)
    risk_weight_path_overlap: float = Field(default=0.30, ge=0, le=1)
    risk_weight_proximity: float = Field(default=0.25, ge=0, le=1)
    risk_weight_approach: float = Field(default=0.20, ge=0, le=1)
    risk_weight_class_severity: float = Field(default=0.15, ge=0, le=1)
    risk_weight_confidence: float = Field(default=0.10, ge=0, le=1)
    risk_class_severities: dict[str, float] = {
        "person": 0.55,
        "chair": 0.75,
        "bag": 0.45,
        "desk": 0.80,
        "bicycle": 0.80,
        "motorcycle": 1.0,
        "car": 0.95,
        "bus": 1.0,
        "bench": 0.65,
    }
    risk_centre_block_threshold: float = Field(default=0.45, ge=0, le=1)
    risk_side_block_threshold: float = Field(default=0.45, ge=0, le=1)
    risk_critical_path_overlap: float = Field(default=0.60, ge=0, le=1)
    risk_critical_proximity: float = Field(default=0.70, ge=0, le=1)
    risk_critical_approach: float = Field(default=0.15, ge=0, le=1)
    alert_persistence_frames: int = Field(default=2, ge=1, le=10)
    alert_clear_frames: int = Field(default=3, ge=1, le=30)
    alert_cooldown_seconds: float = Field(default=3.0, ge=0, le=60)
    decision_margin: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "Settings":
        if self.hazard_person_ttl_seconds >= self.hazard_temporary_ttl_seconds:
            raise ValueError(
                "hazard_person_ttl_seconds must be shorter than "
                "hazard_temporary_ttl_seconds"
            )
        if self.risk_warn_exit >= self.risk_warn_enter:
            raise ValueError("risk_warn_exit must be lower than risk_warn_enter")
        if not (
            self.risk_watch_enter
            < self.risk_warn_enter
            < self.risk_high_enter
        ):
            raise ValueError("risk thresholds must increase from watch to high")
        risk_weight_sum = (
            self.risk_weight_path_overlap
            + self.risk_weight_proximity
            + self.risk_weight_approach
            + self.risk_weight_class_severity
            + self.risk_weight_confidence
        )
        if abs(risk_weight_sum - 1.0) > 1e-6:
            raise ValueError("risk weights must sum to 1.0")
        if not self.risk_class_severities or any(
            value < 0.0 or value > 1.0
            for value in self.risk_class_severities.values()
        ):
            raise ValueError("risk class severities must be normalized")
        if self.corridor_top_half_width >= self.corridor_bottom_half_width:
            raise ValueError(
                "corridor_top_half_width must be below corridor_bottom_half_width"
            )
        if self.wall_side_ratio_threshold > self.wall_centre_ratio_threshold:
            raise ValueError(
                "wall_side_ratio_threshold must not exceed "
                "wall_centre_ratio_threshold"
            )
        if not (
            self.proximity_far_threshold
            < self.proximity_medium_threshold
            < self.proximity_near_threshold
        ):
            raise ValueError("proximity thresholds must increase from far to near")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
