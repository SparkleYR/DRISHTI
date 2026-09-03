package com.drishti.app.walk

import java.time.Instant

/**
 * The five discard rules from API_CONTRACTS.md §8 / ANDROID_APP_SPEC §5.3.
 * A response that fails ANY rule must not touch overlay, speech or haptics.
 */
class FrameFreshnessGate {

    @Volatile
    var latestAppliedFrameId: Int = -1
        private set

    sealed interface Verdict {
        data object Apply : Verdict
        data class Discard(val reason: String) : Verdict
    }

    data class Input(
        val responseSessionId: String,
        val activeSessionId: String?,
        val sessionRunning: Boolean,
        val frameId: Int,
        val overlayValidUntil: Instant,
        val capturedAt: Instant,
        val maxResultAgeMs: Long,
        val now: Instant = Instant.now(),
    )

    fun evaluate(input: Input): Verdict = when {
        input.activeSessionId == null || input.responseSessionId != input.activeSessionId ->
            Verdict.Discard("session_mismatch")
        !input.sessionRunning ->
            Verdict.Discard("session_not_running")
        input.frameId <= latestAppliedFrameId ->
            Verdict.Discard("stale_frame_id")
        input.now.isAfter(input.overlayValidUntil) ->
            Verdict.Discard("overlay_expired")
        input.now.toEpochMilli() - input.capturedAt.toEpochMilli() > input.maxResultAgeMs ->
            Verdict.Discard("result_too_old")
        else -> Verdict.Apply
    }

    fun markApplied(frameId: Int) {
        if (frameId > latestAppliedFrameId) latestAppliedFrameId = frameId
    }

    fun reset() { latestAppliedFrameId = -1 }
}
