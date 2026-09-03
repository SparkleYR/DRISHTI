import type {
  ApiErrorResponse,
  EndWalkSessionResponse,
  FrameAnalysisResponse,
  CreateHazardRequest,
  HazardListResponse,
  HazardResponse,
  ReadTextResponse,
  HealthResponse,
  StartWalkSessionResponse,
} from "@drishti/contracts";
import { File } from "expo-file-system";

const HEALTH_TIMEOUT_MS = 5_000;
const FRAME_ANALYSIS_TIMEOUT_MS = 30_000;

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly code: ApiErrorResponse["error"]["code"],
    readonly retryable: boolean,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export function isConnectionFailure(error: unknown): boolean {
  return error instanceof Error && !(error instanceof ApiRequestError);
}

export async function fetchHealth(baseUrl: string): Promise<HealthResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);

  try {
    const response = await fetch(`${baseUrl}/api/v1/health`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Backend returned HTTP ${response.status}.`);
    }
    return (await response.json()) as HealthResponse;
  } finally {
    clearTimeout(timeout);
  }
}

export async function startWalkSession(baseUrl: string): Promise<StartWalkSessionResponse> {
  return requestJson<StartWalkSessionResponse>(`${baseUrl}/api/v1/walk/sessions`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ device_alias: "expo-phase-6-harness" }),
  });
}

export async function endWalkSession(
  baseUrl: string,
  sessionId: string,
): Promise<EndWalkSessionResponse> {
  return requestJson<EndWalkSessionResponse>(
    `${baseUrl}/api/v1/walk/sessions/${encodeURIComponent(sessionId)}/end`,
    { method: "PATCH", headers: { Accept: "application/json" } },
  );
}

interface AnalyzeFrameInput {
  baseUrl: string;
  sessionId: string;
  frameId: number;
  capturedAt: string;
  imageUri: string;
}

export async function analyzeFrame(input: AnalyzeFrameInput): Promise<FrameAnalysisResponse> {
  const form = new FormData();
  form.append("frame", new File(input.imageUri), `frame-${input.frameId}.jpg`);
  form.append("session_id", input.sessionId);
  form.append("frame_id", String(input.frameId));
  form.append("captured_at", input.capturedAt);
  form.append("rotation_degrees", "0");

  return requestJson<FrameAnalysisResponse>(`${input.baseUrl}/api/v1/walk/analyze`, {
    method: "POST",
    headers: { Accept: "application/json" },
    body: form,
  }, FRAME_ANALYSIS_TIMEOUT_MS);
}

export async function createHazardReport(
  baseUrl: string,
  payload: CreateHazardRequest,
): Promise<HazardResponse> {
  return requestJson<HazardResponse>(`${baseUrl}/api/v1/hazards`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchNearbyHazards(
  baseUrl: string,
  location: { map_id: string; map_version: string; x: number; y: number },
  radius = 0.2,
): Promise<HazardListResponse> {
  const query = new URLSearchParams({
    map_id: location.map_id,
    map_version: location.map_version,
    map_x: String(location.x),
    map_y: String(location.y),
    radius: String(radius),
  });
  return requestJson<HazardListResponse>(`${baseUrl}/api/v1/hazards/nearby?${query}`, {
    headers: { Accept: "application/json" },
  });
}

export async function readText(
  baseUrl: string,
  imageUri: string,
  preferredLanguage = "en",
): Promise<ReadTextResponse> {
  const form = new FormData();
  form.append("frame", new File(imageUri), "explore-read-text.jpg");
  form.append("mode", "READ_TEXT");
  form.append("preferred_language", preferredLanguage);
  return requestJson<ReadTextResponse>(`${baseUrl}/api/v1/explore`, {
    method: "POST",
    headers: { Accept: "application/json" },
    body: form,
  }, 20_000);
}

async function requestJson<T>(url: string, init: RequestInit, timeoutMs = 5_000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const payload = (await response.json()) as T | ApiErrorResponse;
    if (!response.ok) {
      const apiError = payload as ApiErrorResponse;
      throw new ApiRequestError(
        apiError.error?.message ?? `Backend returned HTTP ${response.status}.`,
        apiError.error?.code ?? "INTERNAL_ERROR",
        apiError.error?.retryable ?? false,
        response.status,
      );
    }
    return payload as T;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Local backend request timed out after ${timeoutMs} ms.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
