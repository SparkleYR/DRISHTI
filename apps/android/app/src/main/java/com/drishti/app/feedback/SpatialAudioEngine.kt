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
    }

    fun setEnabled(enabled: Boolean) {
        masterEnabled = enabled
        if (!enabled) voices = emptyList()
    }

    /** Positive yaw = user rotated left, so cues shift right to hold their place. */
    fun applyYaw(yawRad: Float) { yawShift = yawRad * YAW_TO_PAN }

    fun update(newVoices: List<SonarVoice>) {
        voices = if (masterEnabled) newVoices.take(2) else emptyList()
    }

    fun clear() { voices = emptyList() }

    fun updateFromDetections(detections: List<com.drishti.app.net.DetectionResult>) =
        update(SonarMapping.voicesFrom(detections))

    private fun render(out: ShortArray) {
        val active = voices
        if (active.isEmpty()) {
            out.fill(0)
            sampleClock += bufFrames
            return
        }
        val shift = yawShift
        for (i in 0 until bufFrames) {
            val tSec = (sampleClock + i).toDouble() / sampleRate
            var l = 0.0
            var r = 0.0
            for (v in active) {
                val env = if (v.cadenceHz <= 0f) 1.0
                else {
                    val c = 0.5 - 0.5 * cos(2 * PI * v.cadenceHz * tSec)
                    c * c
                }
                val s = sin(2 * PI * v.freqHz * tSec) * v.gain * env
                val pan = (v.pan + shift).coerceIn(-1f, 1f)
                val ang = (pan + 1f) * (PI / 4)      // 0..π/2
                l += s * cos(ang)
                r += s * sin(ang)
            }
            out[i * 2] = toPcm(l)
            out[i * 2 + 1] = toPcm(r)
        }
        sampleClock += bufFrames
    }

    private fun toPcm(v: Double): Short {
        val clamped = max(-1.0, min(1.0, v * 0.8))
        return (clamped * Short.MAX_VALUE).toInt().toShort()
    }

    private companion object {
        const val YAW_TO_PAN = 1.4f
    }
}
