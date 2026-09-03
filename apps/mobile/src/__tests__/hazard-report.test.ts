import type { FrameAnalysisResponse } from "@drishti/contracts";

import { buildAnonymousHazardReport, HALL_DEMO_LOCATION } from "../state/hazardReport";

test("builds an anonymous consent-free report from the strongest risk", () => {
  const result = {
    guidance: { level: "HIGH" },
    detections: [
      { label: "bag", confidence: 0.9, risk_score: 0.3, direction: "LEFT" },
      { label: "chair", confidence: 0.8, risk_score: 0.85, direction: "CENTRE" },
    ],
  } as FrameAnalysisResponse;

  const report = buildAnonymousHazardReport(result, "session-1");

  expect(report).toMatchObject({
    session_id: "session-1",
    category: "chair",
    severity: "HIGH",
    confidence: 0.8,
    risk_score: 0.85,
    direction: "CENTRE",
    map_coordinate: HALL_DEMO_LOCATION,
    temporary: true,
    evidence_consent: false,
  });
  expect(Object.keys(report)).not.toContain("user_id");
});

test("uses a conservative generic record when no detection is present", () => {
  const result = {
    guidance: { level: "CLEAR" },
    detections: [],
  } as unknown as FrameAnalysisResponse;

  expect(buildAnonymousHazardReport(result, "session-2")).toMatchObject({
    category: "path obstruction",
    severity: "LOW",
    confidence: 0.5,
    evidence_consent: false,
  });
});
