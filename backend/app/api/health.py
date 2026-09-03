from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.session import check_database
from app.perception.detector import Detector
from app.perception.segmenter import Segmenter
from app.explore.ocr import OCRReader
from app.explore.local_vlm import VLMEngine
from app.schemas.common import utc_now
from app.schemas.health import (
    ComputeDevice,
    ComputeInfo,
    HealthResponse,
    ModelHealth,
    ModuleHealth,
    ModuleStatus,
    ServiceInfo,
    ServiceStatus,
)


router = APIRouter(prefix="/api/v1", tags=["health"])


def model_health(
    detector: Detector,
    segmenter: Segmenter,
    ocr_reader: OCRReader,
    vlm_engine: VLMEngine,
) -> ModelHealth:
    return ModelHealth(
        detector=ModuleHealth(
            status=ModuleStatus.READY if detector.ready else ModuleStatus.UNAVAILABLE,
            detail=detector.detail,
        ),
        segmentation=ModuleHealth(
            status=ModuleStatus.READY
            if segmenter.ready
            else ModuleStatus.UNAVAILABLE,
            detail=segmenter.detail,
        ),
        tracker=ModuleHealth(
            status=ModuleStatus.READY,
            detail="Session-scoped IoU/centroid tracker ready.",
        ),
        depth=ModuleHealth(
            status=ModuleStatus.DEGRADED,
            detail="Monocular depth unavailable; geometric proximity fallback active.",
        ),
        india_hazards=_hall_hazard_health(detector, segmenter),
        ocr=ModuleHealth(
            status=ModuleStatus.READY
            if ocr_reader.ready
            else ModuleStatus.UNAVAILABLE,
            detail=ocr_reader.detail,
        ),
        vlm=ModuleHealth(
            status=ModuleStatus.READY
            if vlm_engine.ready
            else ModuleStatus.UNAVAILABLE,
            detail=vlm_engine.detail,
        ),
    )


def _hall_hazard_health(
    detector: Detector,
    segmenter: Segmenter,
) -> ModuleHealth:
    if detector.ready and segmenter.ready:
        return ModuleHealth(
            status=ModuleStatus.READY,
            detail=(
                "Indoor hall expansion ready: desk mapping and "
                "wall/dead-end analysis."
            ),
        )
    if detector.ready:
        return ModuleHealth(
            status=ModuleStatus.DEGRADED,
            detail=(
                "Desk mapping remains available; wall/dead-end analysis is "
                "degraded because segmentation is unavailable."
            ),
        )
    if segmenter.ready:
        return ModuleHealth(
            status=ModuleStatus.DEGRADED,
            detail=(
                "Wall/dead-end evidence is available, but Walk Mode and desk "
                "detection are unavailable because the generic detector is not ready."
            ),
        )
    return ModuleHealth(
        status=ModuleStatus.UNAVAILABLE,
        detail="Indoor hall expansion is unavailable with both core models offline.",
    )


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    detector: Detector = request.app.state.detector
    segmenter: Segmenter = request.app.state.segmenter
    ocr_reader: OCRReader = request.app.state.ocr_reader
    vlm_engine: VLMEngine = request.app.state.vlm_engine
    try:
        check_database(request.app.state.database_engine)
        database = ModuleHealth(status=ModuleStatus.READY)
        service_status = ServiceStatus.OK
    except SQLAlchemyError:
        database = ModuleHealth(
            status=ModuleStatus.UNAVAILABLE,
            detail="Local SQLite database is unavailable.",
        )
        service_status = ServiceStatus.DEGRADED

    return HealthResponse(
        server_time=utc_now(),
        status=service_status,
        service=ServiceInfo(version=settings.service_version),
        compute=ComputeInfo(
            selected_device=ComputeDevice(settings.compute_device),
            device_name=settings.compute_device_name,
        ),
        models=model_health(detector, segmenter, ocr_reader, vlm_engine),
        database=database,
        walk_mode_available=detector.ready,
    )
