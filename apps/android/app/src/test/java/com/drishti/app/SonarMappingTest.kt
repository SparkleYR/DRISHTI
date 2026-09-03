package com.drishti.app

import com.drishti.app.feedback.SonarMapping
import com.drishti.app.net.ApproachState
import com.drishti.app.net.Direction
import com.drishti.app.net.DisplayColor
import com.drishti.app.net.DetectionResult
import com.drishti.app.net.NormalizedBoundingBox
import com.drishti.app.net.NormalizedPoint
import com.drishti.app.net.ProximityBand
import com.drishti.app.net.RiskLevel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SonarMappingTest {

    private fun det(
        cx: Double,
        risk: RiskLevel,
        score: Double,
        proximity: ProximityBand = ProximityBand.MEDIUM,
        approach: ApproachState = ApproachState.STATIONARY,
    ) = DetectionResult(
        label = "chair",
        confidence = 0.9,
        bbox = NormalizedBoundingBox(cx - 0.05, 0.4, cx + 0.05, 0.6),
        anchor = NormalizedPoint(cx, 0.6),
        direction = Direction.CENTRE,
        proximity = proximity,
        approachState = approach,
        pathOverlap = 0.5,
        riskScore = score,
        riskLevel = risk,
        displayColor = DisplayColor.YELLOW,
    )

    @Test fun `left object pans left, right object pans right`() {
        val left = SonarMapping.voicesFrom(listOf(det(0.15, RiskLevel.WARN, 0.6))).single()
        val right = SonarMapping.voicesFrom(listOf(det(0.85, RiskLevel.WARN, 0.6))).single()
        assertTrue(left.pan < -0.5f)
        assertTrue(right.pan > 0.5f)
    }

    @Test fun `closer objects raise pitch`() {
        val far = SonarMapping.voicesFrom(listOf(det(0.5, RiskLevel.WARN, 0.6, ProximityBand.FAR))).single()
        val near = SonarMapping.voicesFrom(listOf(det(0.5, RiskLevel.WARN, 0.6, ProximityBand.IMMEDIATE))).single()
        assertTrue(near.freqHz > far.freqHz)
    }

    @Test fun `clear detections are silent and only top two sound`() {
        val voices = SonarMapping.voicesFrom(
            listOf(
                det(0.2, RiskLevel.CLEAR, 0.9),
                det(0.3, RiskLevel.WARN, 0.4),
                det(0.4, RiskLevel.HIGH, 0.8),
                det(0.6, RiskLevel.WATCH, 0.6),
            ),
        )
        assertEquals(2, voices.size)
        // highest score first → HIGH(0.8) then WATCH(0.6)
        assertTrue(voices[0].gain >= voices[1].gain)
    }

    @Test fun `approaching adds an urgency lift`() {
        val still = SonarMapping.voicesFrom(listOf(det(0.5, RiskLevel.WARN, 0.6, ProximityBand.MEDIUM, ApproachState.STATIONARY))).single()
        val coming = SonarMapping.voicesFrom(listOf(det(0.5, RiskLevel.WARN, 0.6, ProximityBand.MEDIUM, ApproachState.APPROACHING))).single()
        assertEquals(80f, coming.freqHz - still.freqHz, 0.01f)
    }
}
