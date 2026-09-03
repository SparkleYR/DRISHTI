import type {
  DashboardAccessibilityResponse,
  DashboardSummaryResponse,
  FrameAnalysisResponse,
  HazardRecord,
  HealthResponse,
  TargetTrackingTelemetry,
} from "@drishti/contracts";

export interface DashboardState {
  accessibility: DashboardAccessibilityResponse;
  health: HealthResponse;
  summary: DashboardSummaryResponse;
  hazards: HazardRecord[];
}

export type EdgeConnectionState = "CONNECTING" | "LIVE" | "UNAVAILABLE";

export interface VramSnapshot {
  usedMib: number;
  freeMib: number;
  totalMib: number;
}

export interface EdgeStreamSnapshot {
  connection: EdgeConnectionState;
  endpoint: string;
  fps: number | null;
  frameAnalysis: FrameAnalysisResponse | null;
  frameUrl: string | null;
  lastEventAt: string | null;
  targetTracking: TargetTrackingTelemetry | null;
  vram: VramSnapshot | null;
}
