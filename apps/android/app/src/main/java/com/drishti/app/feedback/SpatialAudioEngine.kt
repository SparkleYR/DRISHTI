package com.drishti.app.feedback

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Continuous "sonar": up to two steerable sine voices whose stereo position, pitch
 * and pulse rate encode where the nearest hazards are and how urgent they are.
 * A single streaming [AudioTrack] is synthesised in real time so [applyYaw] can
 * nudge the panorama between backend frames (see [GyroSteering]).
 */
class SpatialAudioEngine {

    private val sampleRate = 22_050
    private val bufFrames = 512
    private val stereoBuf = ShortArray(bufFrames * 2)

    @Volatile private var voices: List<SonarVoice> = emptyList()
    @Volatile private var targetVoice: SonarVoice? = null
    private val mix = DoubleArray(2)
    @Volatile private var yawShift: Float = 0f
    @Volatile private var masterEnabled: Boolean = true

    private var track: AudioTrack? = null
    private var scope: CoroutineScope? = null
    private var renderJob: Job? = null
    private var sampleClock = 0L

    fun start() {
        if (track != null) return
        val minBytes = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_STEREO,
            AudioFormat.ENCODING_PCM_16BIT,
        ).coerceAtLeast(bufFrames * 2 * 2 * 4)

        track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(sampleRate)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                    .build(),
            )
            .setBufferSizeInBytes(minBytes)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
            .build()
            .also { it.play() }

        val cs = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        scope = cs
        renderJob = cs.launch {
            val local = track ?: return@launch
            while (isActive) {
                render(stereoBuf)
                local.write(stereoBuf, 0, stereoBuf.size)
            }
        }
    }

    fun stop() {
        renderJob?.cancel()
        scope?.cancel()
        scope = null
        renderJob = null
        runCatching { track?.pause(); track?.flush(); track?.stop(); track?.release() }
        track = null
        voices = emptyList()
        targetVoice = null
    }

    fun setEnabled(enabled: Boolean) {
        masterEnabled = enabled
        if (!enabled) {
            voices = emptyList()
            targetVoice = null
        }
    }

    /** Positive yaw = user rotated left, so cues shift right to hold their place. */
    fun applyYaw(yawRad: Float) { yawShift = yawRad * YAW_TO_PAN }

    fun update(newVoices: List<SonarVoice>) {
        voices = if (masterEnabled) newVoices.take(2) else emptyList()
    }

    fun clear() {
        voices = emptyList()
        targetVoice = null
    }

    /**
     * Ask -> Guide target ping: a single low-gain voice panned to the target's
     * normalized X. Deliberately quiet so it never masks safety speech, and
     * only audible with headphones. Pass null to silence it.
     */
    fun targetPan(normalizedX: Float?) {
        targetVoice = if (masterEnabled && normalizedX != null) {
            SonarVoice(
                freqHz = 700f,
                pan = (normalizedX * 2f - 1f).coerceIn(-1f, 1f),
                gain = 0.22f,
                cadenceHz = 1.1f,
            )
        } else {
            null
        }
    }

    fun updateFromDetections(detections: List<com.drishti.app.net.DetectionResult>) =
        update(SonarMapping.voicesFrom(detections))

    private fun render(out: ShortArray) {
        val active = voices
        val target = targetVoice
        if (active.isEmpty() && target == null) {
            out.fill(0)
            sampleClock += bufFrames
            return
        }
        val shift = yawShift
        for (i in 0 until bufFrames) {
            val tSec = (sampleClock + i).toDouble() / sampleRate
            mix[0] = 0.0
            mix[1] = 0.0
            for (v in active) addVoice(v, tSec, shift, mix)
            if (target != null) addVoice(target, tSec, shift, mix)
            out[i * 2] = toPcm(mix[0])
            out[i * 2 + 1] = toPcm(mix[1])
        }
        sampleClock += bufFrames
    }

    private fun addVoice(v: SonarVoice, tSec: Double, shift: Float, into: DoubleArray) {
        val env = if (v.cadenceHz <= 0f) 1.0
        else {
            val c = 0.5 - 0.5 * cos(2 * PI * v.cadenceHz * tSec)
            c * c
        }
        val s = sin(2 * PI * v.freqHz * tSec) * v.gain * env
        val pan = (v.pan + shift).coerceIn(-1f, 1f)
        val ang = (pan + 1f) * (PI / 4)      // 0..π/2
        into[0] += s * cos(ang)
        into[1] += s * sin(ang)
    }

    private fun toPcm(v: Double): Short {
        val clamped = max(-1.0, min(1.0, v * 0.8))
        return (clamped * Short.MAX_VALUE).toInt().toShort()
    }

    private companion object {
        const val YAW_TO_PAN = 1.4f
    }
}
