interface AdaptiveDelayInput {
  consecutiveFailures: number;
  frameAgeMs?: number;
  maxResultAgeMs: number;
  recommendedFps: number;
  totalProcessingMs?: number;
}

const MIN_DELAY_MS = 100;
const MAX_DELAY_MS = 5_000;

export function adaptiveCaptureDelayMs(input: AdaptiveDelayInput): number {
  const fps = Math.max(0.2, Math.min(5, input.recommendedFps));
  const baseInterval = 1_000 / fps;
  if (input.consecutiveFailures > 0) {
    return Math.min(
      MAX_DELAY_MS,
      Math.round(baseInterval * 2 ** Math.min(input.consecutiveFailures, 4)),
    );
  }

  const processingMs = Math.max(0, input.totalProcessingMs ?? 0);
  let targetInterval = Math.max(baseInterval, processingMs * 1.2);
  if ((input.frameAgeMs ?? 0) > input.maxResultAgeMs * 0.6) {
    targetInterval = Math.max(targetInterval, baseInterval * 1.5, processingMs * 1.5);
  }
  return Math.max(
    MIN_DELAY_MS,
    Math.min(MAX_DELAY_MS, Math.round(targetInterval - processingMs)),
  );
}

export class CaptureLoopGate {
  private activeRequest = false;
  private connectionIncident = false;
  private failures = 0;

  get consecutiveFailures(): number {
    return this.failures;
  }

  get inFlight(): boolean {
    return this.activeRequest;
  }

  tryBegin(): boolean {
    if (this.activeRequest) return false;
    this.activeRequest = true;
    return true;
  }

  finishSuccess(): { connectionRestored: boolean } {
    const connectionRestored = this.connectionIncident;
    this.activeRequest = false;
    this.connectionIncident = false;
    this.failures = 0;
    return { connectionRestored };
  }

  finishConnectionFailure(): { announceConnectionLost: boolean } {
    const announceConnectionLost = !this.connectionIncident;
    this.activeRequest = false;
    this.connectionIncident = true;
    this.failures += 1;
    return { announceConnectionLost };
  }

  finishRequestFailure(): void {
    this.activeRequest = false;
    this.failures += 1;
  }
}
