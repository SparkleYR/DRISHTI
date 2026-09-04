import type {
  CreateHazardRequest,
  DashboardAccessibilityResponse,
  DashboardSummaryResponse,
  HazardListResponse,
  HazardRecord,
  HazardResponse,
  HazardStatus,
  MergeHazardRequest,
  MergeHazardResponse,
  UpdateHazardStatusRequest,
  UpdateHazardStatusResponse,
} from "@drishti/contracts";

import { API_BASE_URL } from "./config";

export async function fetchDashboardSummary(): Promise<DashboardSummaryResponse> {
  return requestJson(`${API_BASE_URL}/api/v1/dashboard/summary`);
}

export async function fetchAccessibility(): Promise<DashboardAccessibilityResponse> {
  return requestJson(`${API_BASE_URL}/api/v1/dashboard/accessibility`);
}

export async function fetchActiveHazards(): Promise<HazardListResponse> {
  return requestJson(`${API_BASE_URL}/api/v1/hazards?active=true&limit=100`);
}

/**
 * File a hazard the coordinator observed themselves.
 *
 * `evidence_consent` is always false: the dashboard has no camera and must never
 * imply a stored image exists (D-046). `confidence` is 1.0 because a person saw
 * this directly rather than a model inferring it. The map identity is passed in
 * by the caller from the live route — never hardcoded here.
 */
export async function createHazard(input: {
  category: string;
  severity: HazardRecord["severity"];
  temporary: boolean;
  mapCoordinate?: CreateHazardRequest["map_coordinate"];
}): Promise<HazardResponse> {
  const payload: CreateHazardRequest = {
    category: input.category,
    severity: input.severity,
    confidence: 1,
    observed_at: new Date().toISOString(),
    temporary: input.temporary,
    evidence_consent: false,
    ...(input.mapCoordinate ? { map_coordinate: input.mapCoordinate } : {}),
  };
  return requestJson(`${API_BASE_URL}/api/v1/hazards`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateHazardStatus(
  hazard: HazardRecord,
  newStatus: HazardStatus,
  operatorAlias: string,
  assignedTo?: string,
): Promise<UpdateHazardStatusResponse> {
  const payload: UpdateHazardStatusRequest = {
    expected_version: hazard.version,
    expected_status: hazard.status,
    new_status: newStatus,
    operator_alias: operatorAlias,
    ...(assignedTo ? { assigned_to: assignedTo } : {}),
  };
  return requestJson(`${API_BASE_URL}/api/v1/hazards/${encodeURIComponent(hazard.id)}/status`, {
    method: "PATCH",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function mergeHazards(
  primary: HazardRecord,
  duplicate: HazardRecord,
  operatorAlias: string,
): Promise<MergeHazardResponse> {
  const payload: MergeHazardRequest = {
    duplicate_hazard_id: duplicate.id,
    expected_primary_version: primary.version,
    expected_duplicate_version: duplicate.version,
    operator_alias: operatorAlias,
  };
  return requestJson(`${API_BASE_URL}/api/v1/hazards/${encodeURIComponent(primary.id)}/merge`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: init?.headers ?? { Accept: "application/json" },
  });
  const payload = await response.json();
  if (!response.ok) {
    const message = payload?.error?.message ?? `Backend returned HTTP ${response.status}.`;
    throw new Error(message);
  }
  return payload as T;
}
