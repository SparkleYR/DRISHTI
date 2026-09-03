from fastapi import APIRouter, Request

from app.hazards.service import HazardService
from app.schemas.hazards import DashboardAccessibilityResponse, DashboardSummaryResponse


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(request: Request) -> DashboardSummaryResponse:
    service: HazardService = request.app.state.hazard_service
    return service.summary()


@router.get("/accessibility", response_model=DashboardAccessibilityResponse)
def dashboard_accessibility(request: Request) -> DashboardAccessibilityResponse:
    service: HazardService = request.app.state.hazard_service
    return service.accessibility()
