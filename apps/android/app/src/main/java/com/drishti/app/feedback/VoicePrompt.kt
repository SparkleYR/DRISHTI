package com.drishti.app.feedback

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import androidx.core.content.ContextCompat
import kotlin.coroutines.resume
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

/**
 * One-shot spoken-question capture for the on-demand VLM scene-description path.
 * This is deliberately separate from the real-time Walk loop: it only runs when
 * the user explicitly asks a question, and it never touches guidance timing.
 *
 * [SpeechRecognizer] must be created and driven on the main thread.
 */
class VoicePrompt(context: Context) {

    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())

    /** True when we have neither a recognizer nor microphone permission. */
    fun blocked(): Boolean = !hasPermission() || !SpeechRecognizer.isRecognitionAvailable(appContext)

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(appContext, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * Listen once and return the top hypothesis, or null on any error / silence /
     * unavailable recognizer. Caller should still apply its own overall timeout.
     */
    suspend fun listen(languageTag: String): String? {
        if (blocked()) return null
        return withContext(Dispatchers.Main) {
            suspendCancellableCoroutine { cont ->
                val recognizer = SpeechRecognizer.createSpeechRecognizer(appContext)
                var settled = false
                fun finish(result: String?) {
                    if (settled) return
                    settled = true
                    runCatching { recognizer.destroy() }
                    if (cont.isActive) cont.resume(result)
                }
                recognizer.setRecognitionListener(object : RecognitionListener {
                    override fun onResults(results: Bundle?) {
                        val best = results
                            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            ?.firstOrNull()
                            ?.trim()
                            ?.ifBlank { null }
                        finish(best)
                    }

                    override fun onError(error: Int) {
                        Log.d(TAG, "recognition error $error")
                        finish(null)
                    }

                    override fun onReadyForSpeech(params: Bundle?) {}
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(rmsdB: Float) {}
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() {}
                    override fun onPartialResults(partialResults: Bundle?) {}
                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })

                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(
                        RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                        RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
                    )
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag)
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
                }

                cont.invokeOnCancellation {
                    main.post { runCatching { recognizer.cancel(); recognizer.destroy() } }
                }

                runCatching { recognizer.startListening(intent) }
                    .onFailure { finish(null) }
            }
        }
    }

    private companion object { const val TAG = "VoicePrompt" }
}
