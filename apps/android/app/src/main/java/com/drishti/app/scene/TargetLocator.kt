package com.drishti.app.scene

import com.drishti.app.R
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.net.ApiResult
import com.drishti.app.net.DrishtiApi
import com.drishti.app.net.apiCall

/**
 * "Ask -> Lock": one Moondream2 locate pass for the active Walk session.
 *
 * No image is uploaded — the backend locates against its own in-memory latest
 * decoded frame for the session (D-068), then hands the box to a CPU tracker.
 * From that point on the per-frame `target_tracking` telemetry in each
 * `/walk/analyze` response drives ongoing speech + haptics (see
 * [com.drishti.app.walk.WalkController.applyTargetTracking]).
 *
 * This call only speaks the one-shot confirmation, which the backend composes
 * ("Registration desk detected at 11 o'clock."); it is spoken verbatim.
 */
class TargetLocator(
    private val api: DrishtiApi,
    private val speech: SpeechEngine,
    private val strings: GuidanceStrings,
) {
    /** @return true when the backend locked a tracker the Walk loop can follow. */
    suspend fun locateOnce(sessionId: String, target: String): Boolean {
        speech.say(strings.string(R.string.locate_working, target), flush = true)
        return when (val r = apiCall { api.vlmLocate(target, sessionId) }) {
            is ApiResult.Ok -> {
                speech.speakBlocking(r.value.text)
                r.value.trackingAllowed
            }
            is ApiResult.Failure -> {
                val line = when (r.code) {
                    "NOT_FOUND" -> strings.string(R.string.locate_not_found, target)
                    "REQUEST_TIMEOUT" -> strings.string(R.string.vlm_timeout)
                    "CONFLICT", "INVALID_REQUEST" -> strings.string(R.string.vlm_busy)
                    else -> strings.string(R.string.locate_unavailable)
                }
                speech.speakBlocking(line, maxWaitMs = 8_000L)
                false
            }
            is ApiResult.Transport -> {
                speech.speakBlocking(strings.string(R.string.conn_lost), maxWaitMs = 8_000L)
                false
            }
        }
    }
}
