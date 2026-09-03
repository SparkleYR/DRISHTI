package com.drishti.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import com.drishti.app.net.DetectionResult
import com.drishti.app.net.DirectionArrow
import com.drishti.app.net.DisplayColor
import com.drishti.app.net.FrameGeometry
import com.drishti.app.net.OverlayContract
import com.drishti.app.ui.theme.DrishtiGreen
import com.drishti.app.ui.theme.DrishtiRed
import com.drishti.app.ui.theme.DrishtiYellow

/**
 * Draws the backend overlay on top of the camera preview: safe / blocked /
 * uncertain regions, detection boxes coloured by display_color, and the
 * direction arrow. All geometry goes through the one [PreviewTransform].
 */
@Composable
fun OverlayCanvas(
    geometry: FrameGeometry?,
    overlay: OverlayContract?,
    detections: List<DetectionResult>,
    modifier: Modifier = Modifier,
) {
    if (geometry == null) return
    Canvas(modifier = modifier.fillMaxSize()) {
        val t = PreviewTransform(
            sourceWidth = geometry.sourceWidth.toFloat(),
            sourceHeight = geometry.sourceHeight.toFloat(),
            previewWidth = size.width,
            previewHeight = size.height,
            resizeMode = PreviewResizeMode.COVER,
        )

        overlay?.let { o ->
            o.safePolygons.forEach { poly -> fillPolygon(t.polygon(poly), DrishtiGreen.copy(alpha = 0.18f)) }
            o.uncertainPolygons.forEach { poly -> fillPolygon(t.polygon(poly), DrishtiYellow.copy(alpha = 0.20f)) }
            o.blockedPolygons.forEach { poly -> fillPolygon(t.polygon(poly), DrishtiRed.copy(alpha = 0.22f)) }
        }

        detections.forEach { d ->
            val r = t.box(d.bbox)
            if (r.width <= 0f || r.height <= 0f) return@forEach
            val color = when (d.displayColor) {
                DisplayColor.GREEN -> DrishtiGreen
                DisplayColor.YELLOW -> DrishtiYellow
                DisplayColor.RED -> DrishtiRed
                DisplayColor.GREY -> Color(0xFFBDBDBD)
            }
            val dashed = d.displayColor == DisplayColor.GREY
            drawRect(
                color = color,
                topLeft = Offset(r.left, r.top),
                size = Size(r.width, r.height),
                style = Stroke(
                    width = 6f,
                    pathEffect = if (dashed) PathEffect.dashPathEffect(floatArrayOf(18f, 14f)) else null,
                ),
            )
        }

        overlay?.directionArrow?.let { arrow ->
            if (arrow != DirectionArrow.NONE) drawArrow(arrow, size)
        }
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.fillPolygon(
    points: List<PreviewTransform.Offset2>,
    color: Color,
) {
    if (points.size < 3) return
    val path = Path().apply {
        moveTo(points.first().x, points.first().y)
        points.drop(1).forEach { lineTo(it.x, it.y) }
        close()
    }
    drawPath(path, color)
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawArrow(
    arrow: DirectionArrow,
    canvas: Size,
) {
    val cx = canvas.width / 2f
    val cy = canvas.height * 0.78f
    val s = canvas.width * 0.12f
    val color = if (arrow == DirectionArrow.STOP) DrishtiRed else DrishtiYellow
    val path = Path()
    when (arrow) {
        DirectionArrow.LEFT -> {
            path.moveTo(cx + s, cy - s); path.lineTo(cx - s, cy); path.lineTo(cx + s, cy + s); path.close()
        }
        DirectionArrow.RIGHT -> {
            path.moveTo(cx - s, cy - s); path.lineTo(cx + s, cy); path.lineTo(cx - s, cy + s); path.close()
        }
        DirectionArrow.STOP -> {
            val h = s * 0.9f
            path.moveTo(cx - h, cy - s); path.lineTo(cx + h, cy - s)
            path.lineTo(cx + s, cy - h); path.lineTo(cx + s, cy + h)
            path.lineTo(cx + h, cy + s); path.lineTo(cx - h, cy + s)
            path.lineTo(cx - s, cy + h); path.lineTo(cx - s, cy - h); path.close()
        }
        DirectionArrow.NONE -> return
    }
    drawPath(path, color)
}
