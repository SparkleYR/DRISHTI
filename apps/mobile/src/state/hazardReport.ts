import type {
  CreateHazardRequest,
  FrameAnalysisResponse,
  HazardSeverity,
  VersionedMapCoordinate,
} from "@drishti/contracts";

export const HALL_DEMO_LOCATION: VersionedMapCoordinate = {
  map_id: "hackathon-demo-hall",
  map_version: "1",
  x: 0.5,
  y: 0.5,
};

export function buildAnonymousHazardReport(
  result: FrameAnalysisResponse,
  sessionId: string,
): CreateHazardRequest {
  const strongest = [...result.detections].sort((a, b) => b.risk_score - a.risk_score)[0];
  return {
    session_id: sessionId,
    category: strongest?.label ?? "path obstruction",
    severity: severityFor(result.guidance.level),
    confidence: strongest?.confidence ?? 0.5,
    risk_score: strongest?.risk_score ?? 0.5,
    direction: strongest?.direction ?? "UNKNOWN",
    observed_at: new Date().toISOString(),
    map_coordinate: HALL_DEMO_LOCATION,
    temporary: true,
    evidence_consent: false,
  };
}

function severityFor(level: FrameAnalysisResponse["guidance"]["level"]): HazardSeverity {
  if (level === "CRITICAL") return "CRITICAL";
  if (level === "HIGH") return "HIGH";
  if (level === "WARN") return "MEDIUM";
  return "LOW";
}
