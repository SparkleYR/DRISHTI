package com.drishti.app.sos

import android.media.AudioManager
import android.media.ToneGenerator
import com.drishti.app.R
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.SpeechEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Local-only emergency mode: loud alternating siren + repeating spoken plea +
 * full-screen SOS banner (rendered by the UI). No network, no SMS, no call.
 */
class SosController(
    private val scope: CoroutineScope,
    private val speech: SpeechEngine,
    private val strings: GuidanceStrings,
) {
    @Volatile var active: Boolean = false
        private set

    private var toneGenerator: ToneGenerator? = null
    private var loopJob: Job? = null

    fun activate() {
        if (active) return
        active = true
        toneGenerator = runCatching {
            ToneGenerator(AudioManager.STREAM_ALARM, ToneGenerator.MAX_VOLUME)
        }.getOrNull()
        loopJob = scope.launch {
            var speakTick = 0
            while (isActive && active) {
                toneGenerator?.startTone(ToneGenerator.TONE_CDMA_HIGH_L, 350)
                delay(450)
                toneGenerator?.startTone(ToneGenerator.TONE_CDMA_LOW_L, 350)
                delay(450)
                if (speakTick % 4 == 0) {
                    speech.say(strings.string(R.string.sos_active), flush = true, dedupe = false)
                }
                speakTick++
            }
        }
    }

    fun cancel() {
        if (!active) return
        active = false
        loopJob?.cancel()
        loopJob = null
        runCatching { toneGenerator?.stopTone(); toneGenerator?.release() }
        toneGenerator = null
        speech.say(strings.string(R.string.sos_cancelled), flush = true)
    }
}
