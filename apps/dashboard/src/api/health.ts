import type { HealthResponse } from "@drishti/contracts";

import { API_BASE_URL } from "./config";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Backend returned HTTP ${response.status}.`);
  }
  return (await response.json()) as HealthResponse;
}

export type GuidanceAction =
  | "CLEAR" | "CAUTION" | "MOVE_LEFT" | "MOVE_RIGHT" | "STOP" | "PAUSE_UNCLEAR";

export interface ActiveWalkSession {
  session_id: string;
  started_at: string;
  last_frame_id: number;
  last_frame_at: string | null;
  last_action: GuidanceAction | null;
  last_risk_level: "CLEAR" | "WATCH" | "WARN" | "HIGH" | "CRITICAL" | null;
}

/**
 * Discover a live Walk session to subscribe to. Session ids are runtime UUIDs,
 * so they cannot be baked into an environment variable.
 */
export async function fetchActiveWalkSessions(): Promise<ActiveWalkSession[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/walk/sessions/active`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Backend returned HTTP ${response.status}.`);
  }
  const payload = (await response.json()) as { sessions?: ActiveWalkSession[] };
  return payload.sessions ?? [];
}
