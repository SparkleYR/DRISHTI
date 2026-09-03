package com.drishti.app.walk

import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToLong

/**
 * Client half of latest-frame-wins: at most one in-flight `/walk/analyze`, an
 * adaptive gap between requests, connection-loss announced once per incident.
 * Ported from apps/mobile/src/state/captureLoop.ts.
 */
object CapturePacing {
    private const val MIN_DELAY_MS = 100L
    private const val MAX_DELAY_MS = 5_000L

    data class Input(
        val consecutiveFailures: Int,
        val frameAgeMs: Double?,
        val maxResultAgeMs: Long,
        val recommendedFps: Double,
        val totalProcessingMs: Double?,
    )

    fun nextDelayMs(input: Input): Long {
        val fps = input.recommendedFps.coerceIn(0.2, 5.0)
        val baseInterval = 1_000.0 / fps
        if (input.consecutiveFailures > 0) {
            val factor = Math.pow(2.0, min(input.consecutiveFailures, 4).toDouble())
            return min(MAX_DELAY_MS, (baseInterval * factor).roundToLong())
        }
        val processing = max(0.0, input.totalProcessingMs ?: 0.0)
        var target = max(baseInterval, processing * 1.2)
        if ((input.frameAgeMs ?: 0.0) > input.maxResultAgeMs * 0.6) {
            target = maxOf(target, baseInterval * 1.5, processing * 1.5)
        }
        return max(MIN_DELAY_MS, min(MAX_DELAY_MS, (target - processing).roundToLong()))
    }
}

/** Mirrors CaptureLoopGate: one active request; connection incident tracked once. */
class CaptureLoopGate {
    @Volatile var inFlight: Boolean = false
        private set
    @Volatile var consecutiveFailures: Int = 0
        private set
    private var connectionIncident = false

    fun tryBegin(): Boolean {
        if (inFlight) return false
        inFlight = true
        return true
    }

    /** @return true if a previously-announced connection loss has now recovered. */
    fun finishSuccess(): Boolean {
        val recovered = connectionIncident
        inFlight = false
        connectionIncident = false
        consecutiveFailures = 0
        return recovered
    }

    /** @return true if this is the first failure of a new connection-loss incident. */
    fun finishConnectionFailure(): Boolean {
        val firstOfIncident = !connectionIncident
        inFlight = false
        connectionIncident = true
        consecutiveFailures += 1
        return firstOfIncident
    }

    fun finishRequestFailure() {
        inFlight = false
        consecutiveFailures += 1
    }

    fun reset() {
        inFlight = false
        consecutiveFailures = 0
        connectionIncident = false
    }
}
