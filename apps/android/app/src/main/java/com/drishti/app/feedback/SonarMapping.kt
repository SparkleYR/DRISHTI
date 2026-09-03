package com.drishti.app.feedback

import com.drishti.app.net.ApproachState
import com.drishti.app.net.DetectionResult
import com.drishti.app.net.ProximityBand
import com.drishti.app.net.RiskLevel

/**
 * Pure mapping from backend detections to steerable audio voices. Kept free of
 * Android imports so it is unit-testable and reused by [SpatialAudioEngine].
 */
data class SonarVoice(
    val freqHz: Float,
    val pan: Float,        // -1 full-left .. +1 full-right (pre-yaw)
    val gain: Float,       // 0..1
    val cadenceHz: Float,  // pulse rate; 0 = steady tone
)

object SonarMapping {
    /** Up to two voices for the highest-risk detections. */
    fun voicesFrom(detections: List<DetectionResult>): List<SonarVoice> =
        detections
            .filter { it.riskLevel != RiskLevel.CLEAR }
            .sortedByDescending { it.riskScore }
            .take(2)
            .map { d ->
                val cx = ((d.bbox.x1 + d.bbox.x2) / 2.0).toFloat()
                val proximityLift = when (d.proximity) {
                    ProximityBand.FAR -> 0f
                    ProximityBand.MEDIUM -> 120f
                    ProximityBand.NEAR -> 280f
                    ProximityBand.IMMEDIATE -> 520f
                    ProximityBand.UNKNOWN -> 0f
                }
                val approachLift = if (d.approachState == ApproachState.APPROACHING) 80f else 0f
                val cadence = when (d.riskLevel) {
                    RiskLevel.WATCH -> 1.5f
                    RiskLevel.WARN -> 2.5f
                    RiskLevel.HIGH -> 5f
                    RiskLevel.CRITICAL -> 7f
                    RiskLevel.CLEAR -> 1f
                }
                val gain = when (d.riskLevel) {
                    RiskLevel.WATCH -> 0.4f
                    RiskLevel.WARN -> 0.7f
                    RiskLevel.HIGH, RiskLevel.CRITICAL -> 1.0f
                    RiskLevel.CLEAR -> 0.2f
                }
                SonarVoice(
                    freqHz = 320f + proximityLift + approachLift,
                    pan = (cx * 2f - 1f).coerceIn(-1f, 1f),
                    gain = gain,
                    cadenceHz = cadence,
                )
            }
}
