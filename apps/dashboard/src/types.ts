import type {
  DashboardAccessibilityResponse,
  DashboardSummaryResponse,
  HazardRecord,
  HealthResponse,
} from "@drishti/contracts";

export interface DashboardState {
  accessibility: DashboardAccessibilityResponse;
  health: HealthResponse;
  summary: DashboardSummaryResponse;
  hazards: HazardRecord[];
}
