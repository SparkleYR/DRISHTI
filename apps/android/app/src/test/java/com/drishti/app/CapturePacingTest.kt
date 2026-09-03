package com.drishti.app

import com.drishti.app.walk.CaptureLoopGate
import com.drishti.app.walk.CapturePacing
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CapturePacingTest {

    @Test fun `base cadence tracks recommended fps`() {
        val d = CapturePacing.nextDelayMs(
            CapturePacing.Input(0, null, 3000, 2.0, 0.0),
        )
        assertTrue("expected ~500ms, got $d", d in 400..520)
    }

    @Test fun `failures back off exponentially and cap`() {
        val d1 = CapturePacing.nextDelayMs(CapturePacing.Input(1, null, 3000, 2.0, null))
        val d3 = CapturePacing.nextDelayMs(CapturePacing.Input(3, null, 3000, 2.0, null))
        assertTrue(d3 > d1)
        val d10 = CapturePacing.nextDelayMs(CapturePacing.Input(10, null, 3000, 2.0, null))
        assertTrue(d10 <= 5000)
    }

    @Test fun `slow processing widens the effective cadence but shrinks the added gap`() {
        val fastGap = CapturePacing.nextDelayMs(CapturePacing.Input(0, null, 3000, 2.0, 50.0))
        val slowGap = CapturePacing.nextDelayMs(CapturePacing.Input(0, null, 3000, 2.0, 900.0))
        // The added gap compensates for elapsed processing, so it is smaller when slow…
        assertTrue(slowGap <= fastGap)
        // …but the request-to-request interval (gap + processing) still grows.
        assertTrue((slowGap + 900) > (fastGap + 50))
    }

    @Test fun `gate allows one in-flight request`() {
        val gate = CaptureLoopGate()
        assertTrue(gate.tryBegin())
        assertFalse(gate.tryBegin())
        gate.finishSuccess()
        assertTrue(gate.tryBegin())
    }

    @Test fun `connection incident announced once then recovery`() {
        val gate = CaptureLoopGate()
        gate.tryBegin()
        assertTrue(gate.finishConnectionFailure())  // first of incident
        gate.tryBegin()
        assertFalse(gate.finishConnectionFailure()) // still same incident
        gate.tryBegin()
        assertTrue(gate.finishSuccess())            // recovered
        assertEquals(0, gate.consecutiveFailures)
    }
}
