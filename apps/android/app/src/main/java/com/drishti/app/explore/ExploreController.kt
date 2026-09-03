package com.drishti.app.explore

import com.drishti.app.R
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.net.ApiResult
import com.drishti.app.net.DrishtiApi
import com.drishti.app.net.OcrConfidenceQualification
import com.drishti.app.net.ReadTextResponse
import com.drishti.app.net.apiCall
import com.drishti.app.walk.CameraFramePipeline
import kotlinx.coroutines.delay
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * On-demand OCR. The caller pauses the Walk loop (mode = READING), invokes this,
 * then resumes. English only — the backend rejects other languages.
 */
class ExploreController(
    private val api: DrishtiApi,
    private val pipeline: CameraFramePipeline,
    private val speech: SpeechEngine,
    private val strings: GuidanceStrings,
) {
    private val jpegType = "image/jpeg".toMediaType()
    private val textType = "text/plain".toMediaType()

    private sealed interface Attempt {
        data class Done(val response: ReadTextResponse) : Attempt
        data object RetryOnce : Attempt
        data object GiveUp : Attempt
    }

    /** @return the read result on success (for on-screen display), else null. */
    suspend fun readTextOnce(): ReadTextResponse? {
        speech.say(strings.string(R.string.explore_listening), flush = true)
        val jpeg = pipeline.captureStill(maxWidth = 2048)
        if (jpeg == null) {
            speech.say(strings.string(R.string.explore_unavailable), flush = true)
            return null
        }
        var attempt = post(jpeg)
        if (attempt is Attempt.RetryOnce) {
            delay(700)
            attempt = post(jpeg)
        }
        return when (attempt) {
            is Attempt.Done -> {
                announce(attempt.response)
                attempt.response
            }
            Attempt.RetryOnce -> {
                speech.say(strings.string(R.string.explore_busy), flush = true)
                null
            }
            Attempt.GiveUp -> null // already voiced
        }
    }

    private suspend fun post(jpeg: ByteArray): Attempt {
        val frame = MultipartBody.Part.createFormData("frame", "explore.jpg", jpeg.toRequestBody(jpegType))
        val mode = "READ_TEXT".toRequestBody(textType)
        val lang = "en".toRequestBody(textType)
        return when (val r = apiCall { api.explore(frame, mode, lang) }) {
            is ApiResult.Ok -> Attempt.Done(r.value)
            is ApiResult.Failure -> {
                if (r.code == "CONFLICT") {
                    Attempt.RetryOnce
                } else {
                    speech.say(strings.string(R.string.explore_unavailable), flush = true)
                    Attempt.GiveUp
                }
            }
            is ApiResult.Transport -> {
                speech.say(strings.string(R.string.conn_lost), flush = true)
                Attempt.GiveUp
            }
        }
    }

    /**
     * Blocking so the caller does not flip back to `WALKING` — and let the Walk
     * loop's next `QUEUE_FLUSH` guidance line cut the readout off — until it has
     * actually been spoken.
     */
    private suspend fun announce(res: ReadTextResponse) {
        val line = when (res.confidenceQualification) {
            OcrConfidenceQualification.NONE -> strings.string(R.string.explore_none)
            OcrConfidenceQualification.LOW -> strings.string(R.string.explore_possible, res.text)
            OcrConfidenceQualification.HIGH -> res.message
        }
        speech.speakBlocking(line, maxWaitMs = 15_000L)
        res.routeNumbers.forEach { route ->
            speech.speakBlocking(
                strings.string(R.string.explore_route, route.toCharArray().joinToString(" ")),
                maxWaitMs = 8_000L,
            )
        }
    }
}
