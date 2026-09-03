from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from starlette.formparsers import MultiPartParser

from app.api.health import router as health_router
from app.api.hazards import router as hazards_router
from app.api.dashboard import router as dashboard_router
from app.api.explore import router as explore_router
from app.api.walk import router as walk_router
from app.api.vlm import router as vlm_router
from app.config import Settings, get_settings
from app.db.session import check_database, create_database_engine
from app.errors import install_error_handlers
from app.logging_config import configure_logging
from app.hazards.service import HazardService
from app.explore.executor import ExploreExecutor
from app.explore.ocr import OCRReader, UnavailableOCRReader, load_ocr_reader
from app.explore.local_vlm import (
    VLMEngine,
    UnavailableVLMEngine,
    load_vlm_engine,
)
from app.explore.vlm_executor import VLMExecutor
from app.perception.detector import Detector, UnavailableDetector, load_detector
from app.perception.segmenter import Segmenter, UnavailableSegmenter, load_segmenter
from app.perception.tracking import TrackingSessionStore
from app.perception.target_tracking import TargetTrackingSessionStore
from app.request_limits import AnalyzeBodyLimitMiddleware
from app.risk.state_machine import RiskSessionStore
from app.scheduling.latest_frame import LatestFrameScheduler
from app.scheduling.frame_memory import LatestFrameMemory
from app.scheduling.telemetry import LatestTelemetryHub
from app.schemas.walk import FrameAnalysisResponse
from app.walk_sessions import WalkSessionStore


logger = logging.getLogger(__name__)


def create_app(
    settings_override: Settings | None = None,
    detector_override: Detector | None = None,
    segmenter_override: Segmenter | None = None,
    ocr_override: OCRReader | None = None,
    vlm_override: VLMEngine | None = None,
) -> FastAPI:
    settings = settings_override or get_settings()
    configure_logging(settings.log_level, settings.log_file)
    database_engine = create_database_engine(settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            check_database(app.state.database_engine)
        except SQLAlchemyError:
            logger.warning("Local SQLite database is unavailable at startup")
        if detector_override is None:
            app.state.detector = load_detector(settings)
        if segmenter_override is None:
            app.state.segmenter = load_segmenter(settings)
        if ocr_override is None:
            app.state.ocr_reader = load_ocr_reader(settings)
        if vlm_override is None:
            app.state.vlm_engine = load_vlm_engine(settings)
        logger.info("Detector status: %s", app.state.detector.detail)
        logger.info("Segmentation status: %s", app.state.segmenter.detail)
        logger.info("OCR status: %s", app.state.ocr_reader.detail)
        logger.info("VLM status: %s", app.state.vlm_engine.detail)
        logger.info("DRISHTI local backend started")
        yield
        app.state.explore_executor.shutdown()
        app.state.vlm_executor.shutdown()
        app.state.vlm_engine.unload()
        app.state.database_engine.dispose()
        logger.info("DRISHTI local backend stopped")

    app = FastAPI(
        title="DRISHTI Local API",
        version=settings.service_version,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database_engine = database_engine
    app.state.hazard_service = HazardService(
        database_engine, settings.evidence_dir, settings
    )
    app.state.walk_sessions = WalkSessionStore()
    app.state.detector = detector_override or UnavailableDetector(
        "Local YOLO11n has not completed startup."
    )
    app.state.segmenter = segmenter_override or UnavailableSegmenter(
        "Local SegFormer-B0 has not completed startup."
    )
    app.state.ocr_reader = ocr_override or UnavailableOCRReader(
        "Local Tesseract has not completed startup."
    )
    app.state.vlm_engine = vlm_override or UnavailableVLMEngine(
        "Local Moondream2 has not completed startup."
    )
    app.state.explore_executor = ExploreExecutor()
    app.state.vlm_executor = VLMExecutor()
    app.state.tracking_sessions = TrackingSessionStore(
        iou_threshold=settings.track_iou_threshold,
        centre_distance_threshold=settings.track_centre_distance_threshold,
        max_age_frames=settings.track_max_age_frames,
    )
    app.state.target_tracking_sessions = TargetTrackingSessionStore(
        confidence_threshold=settings.target_tracking_confidence_threshold,
    )
    app.state.risk_sessions = RiskSessionStore(settings)
    app.state.frame_scheduler = LatestFrameScheduler[FrameAnalysisResponse]()
    app.state.latest_frame_memory = LatestFrameMemory()
    app.state.target_telemetry_hub = LatestTelemetryHub()
    max_analyze_body_bytes = (
        settings.max_image_bytes + settings.max_multipart_overhead_bytes
    )
    max_evidence_body_bytes = (
        settings.max_evidence_image_bytes + settings.max_multipart_overhead_bytes
    )
    max_explore_body_bytes = (
        settings.explore_max_image_bytes + settings.max_multipart_overhead_bytes
    )
    max_vlm_body_bytes = (
        ((settings.vlm_max_image_bytes + 2) // 3) * 4
        + settings.max_multipart_overhead_bytes
    )
    MultiPartParser.spool_max_size = max(
        max_analyze_body_bytes,
        max_evidence_body_bytes,
        max_explore_body_bytes,
        max_vlm_body_bytes,
    ) + 1
    app.add_middleware(
        AnalyzeBodyLimitMiddleware,
        max_body_bytes=max_analyze_body_bytes,
    )
    app.add_middleware(
        AnalyzeBodyLimitMiddleware,
        max_body_bytes=max_evidence_body_bytes,
        paths={"/api/v1/hazards"},
    )
    app.add_middleware(
        AnalyzeBodyLimitMiddleware,
        max_body_bytes=max_explore_body_bytes,
        paths={"/api/v1/explore"},
    )
    app.add_middleware(
        AnalyzeBodyLimitMiddleware,
        max_body_bytes=max_vlm_body_bytes,
        paths={"/api/v1/vlm/query", "/api/v1/vlm/locate"},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Accept", "Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(walk_router)
    app.include_router(hazards_router)
    app.include_router(dashboard_router)
    app.include_router(explore_router)
    app.include_router(vlm_router)
    return app


app = create_app()
