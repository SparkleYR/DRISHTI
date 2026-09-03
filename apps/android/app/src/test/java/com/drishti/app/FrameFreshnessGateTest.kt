package com.drishti.app

import com.drishti.app.walk.FrameFreshnessGate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class FrameFreshnessGateTest {

    private val now = Instant.parse("2026-09-03T12:00:00Z")

    private fun input(
        respSession: String = "S1",
        activeSession: String? = "S1",
        running: Boolean = true,
        frameId: Int = 10,
        validUntil: Instant = now.plusSeconds(2),
        capturedAt: Instant = now.minusMillis(200),
        maxAge: Long = 3000,
    ) = FrameFreshnessGate.Input(
        responseSessionId = respSession,
        activeSessionId = activeSession,
        sessionRunning = running,
        frameId = frameId,
        overlayValidUntil = validUntil,
        capturedAt = capturedAt,
        maxResultAgeMs = maxAge,
        now = now,
    )

    @Test fun `fresh frame applies`() {
        val gate = FrameFreshnessGate()
        assertEquals(FrameFreshnessGate.Verdict.Apply, gate.evaluate(input()))
    }

    @Test fun `rule 1 session mismatch`() {
        val gate = FrameFreshnessGate()
        val v = gate.evaluate(input(respSession = "S2"))
        assertTrue(v is FrameFreshnessGate.Verdict.Discard && v.reason == "session_mismatch")
    }

    @Test fun `rule 2 session not running`() {
        val gate = FrameFreshnessGate()
        val v = gate.evaluate(input(running = false))
        assertTrue(v is FrameFreshnessGate.Verdict.Discard && v.reason == "session_not_running")
    }

    @Test fun `rule 3 non-monotonic frame id`() {
        val gate = FrameFreshnessGate()
        gate.markApplied(20)
        val v = gate.evaluate(input(frameId = 20))
        assertTrue(v is FrameFreshnessGate.Verdict.Discard && v.reason == "stale_frame_id")
    }

    @Test fun `rule 4 overlay expired`() {
        val gate = FrameFreshnessGate()
        val v = gate.evaluate(input(validUntil = now.minusMillis(1)))
        assertTrue(v is FrameFreshnessGate.Verdict.Discard && v.reason == "overlay_expired")
    }

    @Test fun `rule 5 result too old`() {
        val gate = FrameFreshnessGate()
        val v = gate.evaluate(input(capturedAt = now.minusMillis(3200), maxAge = 3000))
        assertTrue(v is FrameFreshnessGate.Verdict.Discard && v.reason == "result_too_old")
    }

    @Test fun `markApplied only advances`() {
        val gate = FrameFreshnessGate()
        gate.markApplied(5)
        gate.markApplied(3)
        assertEquals(5, gate.latestAppliedFrameId)
    }
}
