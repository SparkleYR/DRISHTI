package com.drishti.app.scene

import com.drishti.app.R
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.feedback.VoicePrompt
import com.drishti.app.net.ApiResult
import com.drishti.app.net.DrishtiApi
import com.drishti.app.net.apiCall
import com.drishti.app.walk.CameraFramePipeline
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * On-demand local VLM scene description / Q&A. The user speaks a question, we
 * take one still and POST it to `/api/v1/vlm/query`, then speak the answer.
 *
 * This is the deliberately-slow path: the caller pauses the Walk loop (mode =
 * DESCRIBING), invokes this, then resumes. It never runs automatically and never
 * shares timing with `/walk/analyze`. The backend reloads Moondream2 per request
 * so a full round-trip is typically several seconds.
 */
class SceneDescriber(
    private val api: DrishtiApi,
    private val pipeline: CameraFramePipeline,
    private val speech: SpeechEngine,
    private val strings: GuidanceStrings,
    private val voice: VoicePrompt,
) {
    private val jpegType = "image/jpeg".toMediaType()
    private val textType = "text/plain".toMediaType()

    data class Result(val question: String, val answer: String, val totalMs: Double)

    private sealed interface Attempt {
        data class Done(val text: String, val totalMs: Double) : Attempt
        data object RetryOnce : Attempt
        data object GiveUp : Attempt
    }

    /**
     * @return the answer on success (for on-screen display), else null.
     *
     * Every spoken line here is [SpeechEngine.speakBlocking]: the caller flips
     * back to `WALKING` the instant this returns, and the resumed Walk loop's
     * next guidance line does a `QUEUE_FLUSH`. If we only queued speech, the
     * answer would be cut off mid-sentence and replaced by "STOP, path blocked".
     */
    suspend fun describeOnce(languageTag: String): Result? {
        // 1. Ask the user what they want to know, then open the mic. Wait for
        //    the prompt to finish speaking so the recognizer does not hear it.
        speech.speakBlocking(strings.string(R.string.vlm_prompt_ask), maxWaitMs = 8_000L)
        delay(250)
        val heard =
            if (voice.blocked()) {
                speech.speakBlocking(strings.string(R.string.vlm_mic_denied), maxWaitMs = 8_000L)
                null
            } else {
                withTimeoutOrNull(14_000) { voice.listen(languageTag) }
            }
        val question = heard ?: strings.string(R.string.vlm_default_prompt)
        if (heard == null && !voice.blocked()) {
            speech.speakBlocking(strings.string(R.string.vlm_no_speech), maxWaitMs = 8_000L)
        }

        // 2. "Working on it" is fire-and-forget: the capture + slow round-trip
        //    that follow always outlast it.
        speech.say(strings.string(R.string.vlm_working), flush = true)
        val jpeg = pipeline.captureStill(maxWidth = 1280, quality = 85)
        if (jpeg == null) {
            speech.speakBlocking(strings.string(R.string.vlm_unavailable), maxWaitMs = 8_000L)
            return null
        }

        // 3. Query. One retry if the single VLM worker is momentarily busy.
        var attempt = post(jpeg, question)
        if (attempt is Attempt.RetryOnce) {
            delay(1_500)
            attempt = post(jpeg, question)
        }
        return when (attempt) {
            is Attempt.Done -> {
                speech.speakBlocking(attempt.text)
                Result(question = question, answer = attempt.text, totalMs = attempt.totalMs)
            }
            Attempt.RetryOnce -> {
                speech.speakBlocking(strings.string(R.string.vlm_busy), maxWaitMs = 8_000L)
                null
            }
            Attempt.GiveUp -> null // already voiced (blocking) in post()
        }
    }

    private suspend fun post(jpeg: ByteArray, prompt: String): Attempt {
        val frame = MultipartBody.Part.createFormData("frame", "scene.jpg", jpeg.toRequestBody(jpegType))
        val promptPart = prompt.take(500).toRequestBody(textType)
        return when (val r = apiCall { api.vlmQuery(frame, promptPart) }) {
            is ApiResult.Ok -> Attempt.Done(r.value.text, r.value.timings.totalMs)
            is ApiResult.Failure -> when (r.code) {
                "CONFLICT" -> Attempt.RetryOnce
                "REQUEST_TIMEOUT" -> {
                    speech.speakBlocking(strings.string(R.string.vlm_timeout), maxWaitMs = 8_000L)
                    Attempt.GiveUp
                }
                else -> {
                    speech.speakBlocking(strings.string(R.string.vlm_unavailable), maxWaitMs = 8_000L)
                    Attempt.GiveUp
                }
            }
            is ApiResult.Transport -> {
                speech.speakBlocking(strings.string(R.string.conn_lost), maxWaitMs = 8_000L)
                Attempt.GiveUp
            }
        }
    }
}
