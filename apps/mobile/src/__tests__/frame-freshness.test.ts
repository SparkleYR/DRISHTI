import type { FrameAnalysisResponse } from "@drishti/contracts";

import { shouldApplyFrameResult } from "../state/frameFreshness";


const NOW = Date.parse("2026-09-03T12:00:00.500Z");

function result(overrides: Partial<FrameAnalysisResponse> = {}): FrameAnalysisResponse {
  return {
    session_id: "active",
    frame_id: 4,
    captured_at: "2026-09-03T12:00:00.000Z",
    overlay: { valid_until: "2026-09-03T12:00:01.000Z" },
    ...overrides,
  } as FrameAnalysisResponse;
}

const context = {
  activeSessionId: "active",
  latestAppliedFrameId: 3,
  maxResultAgeMs: 1_000,
  nowMs: NOW,
  sessionActive: true,
};

test("accepts the next fresh result for the active session", () => {
  expect(shouldApplyFrameResult(result(), context)).toBe(true);
});

test("rejects results for another, paused, or ended session", () => {
  expect(shouldApplyFrameResult(result({ session_id: "other" }), context)).toBe(false);
  expect(shouldApplyFrameResult(result(), { ...context, sessionActive: false })).toBe(false);
});

test("rejects an already applied or out-of-order frame", () => {
  expect(shouldApplyFrameResult(result({ frame_id: 3 }), context)).toBe(false);
  expect(shouldApplyFrameResult(result({ frame_id: 2 }), context)).toBe(false);
});

test("rejects an expired overlay", () => {
  expect(shouldApplyFrameResult(result({
    overlay: { valid_until: "2026-09-03T12:00:00.499Z" } as FrameAnalysisResponse["overlay"],
  }), context)).toBe(false);
});

test("rejects a result older than the session freshness limit", () => {
  expect(shouldApplyFrameResult(result({
    captured_at: "2026-09-03T11:59:59.000Z",
  }), context)).toBe(false);
});
