package com.drishti.app

import com.drishti.app.net.NormalizedBoundingBox
import com.drishti.app.net.NormalizedPoint
import com.drishti.app.ui.PreviewResizeMode
import com.drishti.app.ui.PreviewTransform
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PreviewTransformTest {

    @Test fun `identity when preview matches source`() {
        val t = PreviewTransform(100f, 200f, 100f, 200f, PreviewResizeMode.CONTAIN)
        val p = t.point(NormalizedPoint(0.5, 0.25))
        assertEquals(50f, p.x, 0.001f)
        assertEquals(50f, p.y, 0.001f)
    }

    @Test fun `corners map to preview edges under contain`() {
        val t = PreviewTransform(4f, 3f, 400f, 300f, PreviewResizeMode.CONTAIN)
        val tl = t.point(NormalizedPoint(0.0, 0.0))
        val br = t.point(NormalizedPoint(1.0, 1.0))
        assertEquals(0f, tl.x, 0.001f)
        assertEquals(0f, tl.y, 0.001f)
        assertEquals(400f, br.x, 0.001f)
        assertEquals(300f, br.y, 0.001f)
    }

    @Test fun `cover crops the longer axis symmetrically`() {
        // Source 1:1 into a 100x200 preview: COVER scales to fill height, x overflows.
        val t = PreviewTransform(100f, 100f, 100f, 200f, PreviewResizeMode.COVER)
        val centre = t.point(NormalizedPoint(0.5, 0.5))
        assertEquals(50f, centre.x, 0.001f)
        assertEquals(100f, centre.y, 0.001f)
        val left = t.point(NormalizedPoint(0.0, 0.5))
        assertEquals(-50f, left.x, 0.001f) // overflow is expected and clamped by box()
    }

    @Test fun `box is clamped to the visible preview`() {
        val t = PreviewTransform(100f, 100f, 100f, 200f, PreviewResizeMode.COVER)
        val r = t.box(NormalizedBoundingBox(0.0, 0.0, 1.0, 1.0))
        assertTrue(r.left >= 0f)
        assertTrue(r.left + r.width <= 100f + 0.001f)
        assertTrue(r.height > 0f)
    }
}
