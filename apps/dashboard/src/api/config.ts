/**
 * Single source of truth for the local backend the dashboard talks to.
 *
 * DRISHTI is local-only (AGENTS.md), so these default to loopback: the
 * dashboard runs on the same laptop as the backend. Override per machine with
 * `apps/dashboard/.env` — never hardcode a LAN address in source, because the
 * laptop's IP changes with the network and the phone's address is configured
 * separately in the Android client.
 */

function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
);

/**
 * Base for the Walk telemetry WebSocket, derived from `API_BASE_URL` so the two
 * can never drift apart. `VITE_STREAM_WS_URL` still overrides it outright for
 * the case where telemetry is served from somewhere else.
 */
export const STREAM_WS_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_STREAM_WS_URL || API_BASE_URL.replace(/^http/, "ws"),
);
