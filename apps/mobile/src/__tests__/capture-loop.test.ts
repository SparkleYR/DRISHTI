import { adaptiveCaptureDelayMs, CaptureLoopGate } from "../state/captureLoop";
import { ApiRequestError, isConnectionFailure } from "../api/client";


test("permits only one in-flight request", () => {
  const gate = new CaptureLoopGate();

  expect(gate.tryBegin()).toBe(true);
  expect(gate.inFlight).toBe(true);
  expect(gate.tryBegin()).toBe(false);
  gate.finishSuccess();
  expect(gate.tryBegin()).toBe(true);
});

test("announces connection loss once and reports recovery", () => {
  const gate = new CaptureLoopGate();
  gate.tryBegin();
  expect(gate.finishConnectionFailure().announceConnectionLost).toBe(true);
  gate.tryBegin();
  expect(gate.finishConnectionFailure().announceConnectionLost).toBe(false);
  gate.tryBegin();
  expect(gate.finishSuccess().connectionRestored).toBe(true);
  gate.tryBegin();
  expect(gate.finishConnectionFailure().announceConnectionLost).toBe(true);
});

test("adapts pacing to processing pressure, freshness, and retry backoff", () => {
  const normal = adaptiveCaptureDelayMs({
    consecutiveFailures: 0,
    frameAgeMs: 200,
    maxResultAgeMs: 1_000,
    recommendedFps: 2,
    totalProcessingMs: 200,
  });
  const stalePressure = adaptiveCaptureDelayMs({
    consecutiveFailures: 0,
    frameAgeMs: 800,
    maxResultAgeMs: 1_000,
    recommendedFps: 2,
    totalProcessingMs: 200,
  });
  const firstRetry = adaptiveCaptureDelayMs({
    consecutiveFailures: 1,
    maxResultAgeMs: 1_000,
    recommendedFps: 2,
  });
  const laterRetry = adaptiveCaptureDelayMs({
    consecutiveFailures: 4,
    maxResultAgeMs: 1_000,
    recommendedFps: 2,
  });

  expect(normal).toBe(300);
  expect(stalePressure).toBe(550);
  expect(firstRetry).toBe(1_000);
  expect(laterRetry).toBe(5_000);
});

test("distinguishes typed backend responses from connection failures", () => {
  expect(isConnectionFailure(new TypeError("Network request failed"))).toBe(true);
  expect(isConnectionFailure(new ApiRequestError("Old frame", "FRAME_TOO_OLD", true, 409))).toBe(false);
});
