package com.drishti.app.ui

import com.drishti.app.net.NormalizedBoundingBox
import com.drishti.app.net.NormalizedPoint
import kotlin.math.max
import kotlin.math.min

/**
 * The single ORIENTED_CAPTURE_NORMALIZED → preview-pixel transform
 * (ANDROID_APP_SPEC §3.7). Ported from apps/mobile/src/overlay/transform.ts.
 * Because the app sends an already-upright JPEG, no rotation term is needed here.
 */
enum class PreviewResizeMode { COVER, CONTAIN }

data class PreviewTransform(
    val sourceWidth: Float,
    val sourceHeight: Float,
    val previewWidth: Float,
    val previewHeight: Float,
    val resizeMode: PreviewResizeMode = PreviewResizeMode.COVER,
) {
    private val scale: Float
    private val offsetX: Float
    private val offsetY: Float

    init {
        require(sourceWidth > 0 && sourceHeight > 0 && previewWidth > 0 && previewHeight > 0) {
            "preview and source dimensions must be positive"
        }
        val sx = previewWidth / sourceWidth
        val sy = previewHeight / sourceHeight
        scale = if (resizeMode == PreviewResizeMode.COVER) max(sx, sy) else min(sx, sy)
        offsetX = (previewWidth - sourceWidth * scale) / 2f
        offsetY = (previewHeight - sourceHeight * scale) / 2f
    }

    fun point(p: NormalizedPoint): Offset2 {
        val nx = p.x.toFloat().coerceIn(0f, 1f)
        val ny = p.y.toFloat().coerceIn(0f, 1f)
        return Offset2(
            x = offsetX + nx * sourceWidth * scale,
            y = offsetY + ny * sourceHeight * scale,
        )
    }

    fun box(b: NormalizedBoundingBox): Rect2 {
        val tl = point(NormalizedPoint(min(b.x1, b.x2), min(b.y1, b.y2)))
        val br = point(NormalizedPoint(max(b.x1, b.x2), max(b.y1, b.y2)))
        val left = max(0f, tl.x)
        val top = max(0f, tl.y)
        val right = min(previewWidth, br.x)
        val bottom = min(previewHeight, br.y)
        return Rect2(left, top, (right - left).coerceAtLeast(0f), (bottom - top).coerceAtLeast(0f))
    }

    fun polygon(points: List<NormalizedPoint>): List<Offset2> = points.map { point(it) }

    data class Offset2(val x: Float, val y: Float)
    data class Rect2(val left: Float, val top: Float, val width: Float, val height: Float)
}
