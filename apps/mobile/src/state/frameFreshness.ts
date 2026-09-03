import type { FrameAnalysisResponse } from "@drishti/contracts";


interface FreshnessContext {
  activeSessionId: string | null;
  latestAppliedFrameId: number;
  maxResultAgeMs: number;
  nowMs: number;
  sessionActive: boolean;
}

export function shouldApplyFrameResult(
  result: FrameAnalysisResponse,
  context: FreshnessContext,
): boolean {
  if (!context.sessionActive || result.session_id !== context.activeSessionId) return false;
  if (result.frame_id <= context.latestAppliedFrameId) return false;

  const capturedAtMs = Date.parse(result.captured_at);
  const validUntilMs = Date.parse(result.overlay.valid_until);
  if (!Number.isFinite(capturedAtMs) || !Number.isFinite(validUntilMs)) return false;
  if (context.nowMs > validUntilMs) return false;
  return context.nowMs - capturedAtMs <= context.maxResultAgeMs;
}
