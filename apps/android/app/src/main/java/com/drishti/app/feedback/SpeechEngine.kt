package com.drishti.app.feedback

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Self-driven speech.
 *
 * Android 16 "audio hardening" mutes playback attributed to a background app —
 * and TextToSpeech audio is attributed to the TTS engine process, which is
 * always background. The only reliable way to stay audible is for DRISHTI itself
 * to hold audio focus while it is speaking, so this engine owns a transient
 * (may-duck) focus request around every utterance and drops it a moment after
 * the queue drains. Usage is NAVIGATION_GUIDANCE so it is audible even with no
 * accessibility service running, while still ducking media and coexisting with
 * TalkBack (which uses its own stream).
 */
class SpeechEngine(context: Context) {

    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val ready = AtomicBoolean(false)
    private var pendingLanguage: SpokenLanguage = SpokenLanguage.ENGLISH
    private var pendingRate: Float = 0.5f
    private var lastSpoken: String? = null

    /** init status, exposed for the on-screen diagnostics line. */
    @Volatile var initError: String? = "starting"
        private set

    private val audioManager =
        appContext.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private val speechAttrs = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    private val focusRequest = AudioFocusRequest.Builder(
        AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK,
    )
        .setAudioAttributes(speechAttrs)
        .setWillPauseWhenDucked(false)
        .setOnAudioFocusChangeListener({ }, main)
        .build()

    private val outstanding = AtomicInteger(0)
    private val focusHeld = AtomicBoolean(false)
    private val releaseFocusRunnable = Runnable { releaseFocus() }

    /** utteranceId -> completion, for [speakBlocking]. */
    private val awaiters = ConcurrentHashMap<String, CompletableDeferred<Unit>>()

    private val tts: TextToSpeech = TextToSpeech(appContext) { status -> onInit(status) }

    private fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) {
            initError = "engine unavailable ($status)"
            Log.w(TAG, "TextToSpeech init failed: $status")
            return
        }
        tts.setAudioAttributes(speechAttrs)
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) = utteranceFinished(utteranceId)
            @Deprecated("legacy") override fun onError(utteranceId: String?) = utteranceFinished(utteranceId)
            override fun onError(utteranceId: String?, errorCode: Int) = utteranceFinished(utteranceId)
            override fun onStop(utteranceId: String?, interrupted: Boolean) = utteranceFinished(utteranceId)
        })
        ready.set(true)
        initError = null
        applyLanguage(pendingLanguage)
        applyRate(pendingRate)
    }

    fun setLanguage(language: SpokenLanguage) {
        pendingLanguage = language
        if (ready.get()) applyLanguage(language)
    }

    fun setRate(rate01: Float) {
        pendingRate = rate01
        if (ready.get()) applyRate(rate01)
    }

    /**
     * A blind mobility aid must not be silent because the media slider is down.
     * If STREAM_MUSIC (where navigation-guidance speech is routed) is very low,
     * raise it to a usable level. Only ever raises, never lowers; safe to call
     * often. No-op if a Do Not Disturb policy blocks the change.
     */
    fun ensureAudible() {
        runCatching {
            val max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            val cur = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC)
            if (cur < max * 0.4f) {
                audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, (max * 0.6f).toInt(), 0)
            }
        }
    }

    private fun applyLanguage(language: SpokenLanguage) {
        val result = tts.setLanguage(language.locale)
        if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
            Log.w(TAG, "TTS locale ${language.locale} unavailable; falling back to English")
            tts.language = Locale.ENGLISH
        }
    }

    private fun applyRate(rate01: Float) {
        tts.setSpeechRate(0.6f + rate01.coerceIn(0f, 1f) * 1.2f)
    }

    fun say(text: String?, flush: Boolean = false, dedupe: Boolean = true) {
        val phrase = text?.trim().orEmpty()
        if (phrase.isEmpty() || !ready.get()) return
        if (dedupe && !flush && phrase == lastSpoken) return
        lastSpoken = phrase
        acquireFocus()
        outstanding.incrementAndGet()
        val mode = if (flush) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
        tts.speak(phrase, mode, null, "drishti-${System.nanoTime()}")
    }

    /**
     * Speak [text] and suspend until that utterance actually finishes (or
     * [maxWaitMs] elapses). Used by the on-demand VLM path so the caller does
     * not resume the Walk loop — whose next guidance line would `QUEUE_FLUSH`
     * and cut the answer off mid-sentence — until the answer has been said.
     */
    suspend fun speakBlocking(text: String?, maxWaitMs: Long = 45_000L) {
        val phrase = text?.trim().orEmpty()
        if (phrase.isEmpty() || !ready.get()) return
        lastSpoken = phrase
        val id = "drishti-await-${System.nanoTime()}"
        val done = CompletableDeferred<Unit>()
        awaiters[id] = done
        acquireFocus()
        outstanding.incrementAndGet()
        val queued = runCatching {
            tts.speak(phrase, TextToSpeech.QUEUE_FLUSH, null, id)
        }.getOrDefault(TextToSpeech.ERROR)
        if (queued != TextToSpeech.SUCCESS) {
            awaiters.remove(id)
            utteranceFinished(null) // balance the increment above
            return
        }
        try {
            withTimeoutOrNull(maxWaitMs) { done.await() }
        } finally {
            awaiters.remove(id)
        }
    }

    fun repeatLast(): Boolean {
        val last = lastSpoken ?: return false
        acquireFocus()
        outstanding.incrementAndGet()
        tts.speak(last, TextToSpeech.QUEUE_FLUSH, null, "drishti-repeat-${System.nanoTime()}")
        return true
    }

    fun stop() {
        if (ready.get()) tts.stop()
        drainAwaiters()
        outstanding.set(0)
        releaseFocus()
    }

    fun shutdown() {
        runCatching { tts.stop() }
        runCatching { tts.shutdown() }
        drainAwaiters()
        ready.set(false)
        releaseFocus()
    }

    private fun drainAwaiters() {
        val pending = awaiters.values.toList()
        awaiters.clear()
        pending.forEach { it.complete(Unit) }
    }

    private fun utteranceFinished(utteranceId: String? = null) {
        if (utteranceId != null) awaiters.remove(utteranceId)?.complete(Unit)
        if (outstanding.decrementAndGet() <= 0) {
            outstanding.set(0)
            // brief lease so back-to-back utterances don't thrash focus
            main.removeCallbacks(releaseFocusRunnable)
            main.postDelayed(releaseFocusRunnable, 1_200)
        }
    }

    private fun acquireFocus() {
        main.removeCallbacks(releaseFocusRunnable)
        if (focusHeld.compareAndSet(false, true)) {
            runCatching { audioManager.requestAudioFocus(focusRequest) }
        }
    }

    private fun releaseFocus() {
        if (focusHeld.compareAndSet(true, false)) {
            runCatching { audioManager.abandonAudioFocusRequest(focusRequest) }
        }
    }

    private companion object { const val TAG = "SpeechEngine" }
}
