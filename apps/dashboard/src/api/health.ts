import type { HealthResponse } from "@drishti/contracts";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Backend returned HTTP ${response.status}.`);
  }
  return (await response.json()) as HealthResponse;
}
