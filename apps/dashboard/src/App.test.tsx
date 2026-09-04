import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

const HEALTH = {
  schema_version: "1.0.0",
  server_time: "2026-09-03T12:00:00.000Z",
  status: "OK",
  runtime_mode: "LOCAL_ONLY",
  service: { name: "drishti-backend", version: "0.1.0" },
  compute: { selected_device: "CUDA", device_name: "Test GPU" },
  models: Object.fromEntries(
    ["detector", "segmentation", "tracker", "depth", "india_hazards", "ocr", "vlm"].map((name) => [
      name,
      { status: "READY" },
    ]),
  ),
  database: { status: "READY" },
  walk_mode_available: true,
};

const HAZARD = {
  id: "hazard-1",
  category: "chair obstruction",
  severity: "HIGH",
  status: "NEW",
  map_coordinate: { map_id: "phase6-test-map", map_version: "1", x: 0.5, y: 0.5 },
  first_seen_at: "2026-09-03T12:00:00.000Z",
  last_seen_at: "2026-09-03T12:00:00.000Z",
  confidence: 0.88,
  confirmation_count: 1,
  temporary: true,
  version: 1,
  has_consented_evidence: false,
};

const SUMMARY = {
  schema_version: "1.0.0",
  server_time: "2026-09-03T12:00:00.000Z",
  counts: { new: 1, verified: 0, assigned: 0, in_progress: 0, resolved: 0, rejected: 0 },
  active_verified_hazards: 0,
  awaiting_review: 1,
  recently_resolved: [],
};

const ACCESSIBILITY = {
  schema_version: "1.0.0",
  server_time: "2026-09-03T12:00:00.000Z",
  advisory_only: true,
  disclaimer: "Operational hall score only. It is not live navigation.",
  expired_temporary_count: 2,
  routes: [
    {
      route_id: "hall-obstacle-course-v1",
      route_key: "hall-obstacle-course",
      route_name: "Hall Obstacle Course",
      description: "Controlled judging route",
      map_id: "hackathon-demo-hall",
      map_version: "1",
      specification_version: "1.0.0",
      score: 72.5,
      band: "MODERATE_ACCESS",
      active_hazard_count: 1,
      recurring_hazard_count: 1,
      segments: [
        {
          segment: {
            id: "main",
            segment_key: "main",
            name: "Main hall aisle",
            sequence: 1,
            start: { map_id: "hackathon-demo-hall", map_version: "1", x: 0.5, y: 0.9 },
            end: { map_id: "hackathon-demo-hall", map_version: "1", x: 0.5, y: 0.1 },
            corridor_radius: 0.13,
          },
          score: 72.5,
          band: "MODERATE_ACCESS",
          factors: [
            {
              hazard_id: "hazard-1",
              category: "chair obstruction",
              severity: "HIGH",
              status: "VERIFIED",
              confirmation_count: 3,
              confidence: 0.88,
              temporary: true,
              age_seconds: 10,
              distance_to_segment: 0,
              severity_points: 28,
              status_factor: 1,
              recurrence_factor: 1.2,
              confidence_factor: 0.94,
              freshness_factor: 0.98,
              spatial_factor: 1,
              penalty_points: 27.5,
              explanation: "chair obstruction: high severity, 3 observation(s), 88% confidence.",
            },
          ],
        },
      ],
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  value: () => null,
});

function walkSession(overrides: Record<string, unknown> = {}) {
  return {
    session_id: "ab12cd34-0000-0000-0000-000000000000",
    started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    last_frame_id: 42,
    last_frame_at: new Date().toISOString(),
    last_action: "CLEAR",
    last_risk_level: "CLEAR",
    ...overrides,
  };
}

function jsonResponse(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

function installFetch(sessions: unknown[] = []) {
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "PATCH") {
      return jsonResponse({
        schema_version: "1.0.0",
        server_time: SUMMARY.server_time,
        hazard: { ...HAZARD, status: "VERIFIED", version: 2 },
        transition: {},
      });
    }
    if (url.endsWith("/api/v1/health")) return jsonResponse(HEALTH);
    if (url.endsWith("/api/v1/dashboard/summary")) return jsonResponse(SUMMARY);
    if (url.endsWith("/api/v1/dashboard/accessibility")) return jsonResponse(ACCESSIBILITY);
    if (url.endsWith("/api/v1/walk/sessions/active")) {
      return jsonResponse({ schema_version: "1.0.0", server_time: SUMMARY.server_time, sessions });
    }
    if (url.includes("/api/v1/hazards?")) {
      return jsonResponse({ schema_version: "1.0.0", server_time: SUMMARY.server_time, items: [HAZARD] });
    }
    throw new Error(`Unexpected URL: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

test("leads with who is walking, then readiness, work queue, and the map", async () => {
  installFetch([walkSession()]);
  render(<App />);

  await waitFor(() => expect(screen.getByText("People out walking")).toBeTruthy());
  expect(screen.getByText("Device AB")).toBeTruthy();
  expect(screen.getByText("Path is clear")).toBeTruthy();
  expect(screen.getByText("Ready — people can walk")).toBeTruthy();
  expect(screen.getByText("Reports to act on")).toBeTruthy();
  expect(screen.getByText("Where the hazards are")).toBeTruthy();
  expect(screen.getByRole("img", { name: /Walking route with 1 hazard marked/ })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Verify" })).toBeTruthy();
});

test("says plainly when nobody is walking", async () => {
  installFetch([]);
  render(<App />);

  await waitFor(() => expect(screen.getByText("Nobody walking")).toBeTruthy());
  expect(screen.getByText(/Nobody is walking right now/)).toBeTruthy();
});

test("flags a walker whose phone has gone quiet", async () => {
  installFetch([
    walkSession({ last_frame_at: new Date(Date.now() - 30_000).toISOString() }),
  ]);
  render(<App />);

  await waitFor(() => expect(screen.getByText(/No signal for/)).toBeTruthy());
  expect(screen.getByRole("status").textContent).toContain("Someone may need help");
});

test("flags a walker who was told to stop", async () => {
  installFetch([walkSession({ last_action: "STOP", last_risk_level: "CRITICAL" })]);
  render(<App />);

  await waitFor(() => expect(screen.getByText("Stop — something ahead")).toBeTruthy());
  expect(screen.getByRole("status").textContent).toContain("Someone may need help");
});

test("keeps engineering detail behind a disclosure", async () => {
  installFetch([]);
  render(<App />);

  await waitFor(() => expect(screen.getByText("Ready — people can walk")).toBeTruthy());
  // Model and hardware names are not on screen until the operator asks.
  expect(screen.queryByText("Test GPU")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: /Technical details/ }));
  expect(screen.getByText("Test GPU")).toBeTruthy();
  expect(screen.getByText("Obstacle detection")).toBeTruthy();
});

test("provides functional text size accessibility controls", async () => {
  installFetch([]);
  render(<App />);

  const largerText = screen.getByRole("button", { name: "Set text size A+" });
  fireEvent.click(largerText);
  expect(document.documentElement.style.fontSize).toBe("112%");
  expect(largerText.getAttribute("aria-pressed")).toBe("true");

  fireEvent.click(screen.getByRole("button", { name: "Set text size A" }));
  expect(document.documentElement.style.fontSize).toBe("100%");
});

test("renders an understandable failure when the backend is unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Connection refused")));
  render(<App />);

  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Cannot reach the system"));
  expect(screen.getByRole("alert").textContent).toContain("Connection refused");
});

test("sends optimistic status transition fields", async () => {
  const fetchMock = installFetch([]);
  render(<App />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Verify" })).toBeTruthy());

  fireEvent.click(screen.getByRole("button", { name: "Verify" }));
  await waitFor(() => {
    const patchCall = fetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
    expect(patchCall).toBeTruthy();
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      expected_version: 1,
      expected_status: "NEW",
      new_status: "VERIFIED",
      operator_alias: "access-desk",
    });
  });
});
