package com.drishti.app.feedback

import android.content.Context
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import com.drishti.app.net.GuidanceAction
import com.drishti.app.net.HapticPattern

/**
 * The "waveform language" from ANDROID_APP_SPEC §7.1. Directional warnings lean
 * left/right by lengthening the leading gap on the opposite side.
 */
class HapticEngine(context: Context) {

    private val vibrator: Vibrator =
        (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator

    @Volatile var enabled: Boolean = true

    fun ack() {
        if (!enabled || !vibrator.hasVibrator()) return
        vibrator.vibrate(VibrationEffect.createOneShot(15, 120))
    }

    fun play(pattern: HapticPattern, action: GuidanceAction = GuidanceAction.CLEAR) {
        if (!enabled || !vibrator.hasVibrator()) return
        val effect = when (pattern) {
            HapticPattern.NONE -> return
            HapticPattern.CAUTION_SHORT ->
                VibrationEffect.createWaveform(longArrayOf(0, 40), intArrayOf(0, 140), -1)
            HapticPattern.WARNING_DOUBLE -> directionalDouble(action)
            HapticPattern.CRITICAL_RAPID ->
                VibrationEffect.createWaveform(
                    longArrayOf(0, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50),
                    intArrayOf(0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255),
                    -1,
                )
            HapticPattern.UNCLEAR_LONG ->
                VibrationEffect.createWaveform(longArrayOf(0, 400), intArrayOf(0, 90), -1)
        }
        vibrator.cancel()
        vibrator.vibrate(effect)
    }

    private fun directionalDouble(action: GuidanceAction): VibrationEffect {
        // Symmetric base double-pulse; bias the opening gap toward the target side.
        val lead = when (action) {
            GuidanceAction.MOVE_LEFT -> 0L
            GuidanceAction.MOVE_RIGHT -> 120L
            else -> 60L
        }
        return VibrationEffect.createWaveform(
            longArrayOf(lead, 60, 80, 60),
            intArrayOf(0, 200, 0, 200),
            -1,
        )
    }

    fun cancel() = vibrator.cancel()
}
