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
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.sp
import com.drishti.app.net.DetectionResult
import com.drishti.app.net.DirectionArrow
import com.drishti.app.net.DisplayColor
import com.drishti.app.net.FrameGeometry
import com.drishti.app.net.OverlayContract
import com.drishti.app.ui.theme.DrishtiGreen
import com.drishti.app.ui.theme.DrishtiRed
import com.drishti.app.ui.theme.DrishtiYellow
import kotlin.math.roundToInt

/**
 * Draws the backend overlay on top of the camera preview: safe / blocked /
 * uncertain regions, detection boxes coloured by display_color, a small label
 * chip per box ("<what> <confidence>%"), and the direction arrow. All geometry
 * goes through the one [PreviewTransform].
 */
@Composable
fun OverlayCanvas(
    geometry: FrameGeometry?,
    overlay: OverlayContract?,
    detections: List<DetectionResult>,
    modifier: Modifier = Modifier,
) {
    if (geometry == null) return
    val textMeasurer = rememberTextMeasurer()
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
            drawDetectionLabel(
                measurer = textMeasurer,
                text = "${d.label} ${(d.confidence * 100.0).roundToInt()}%",
                box = r,
                chipColor = color,
                canvas = size,
            )
        }

        overlay?.directionArrow?.let { arrow ->
            if (arrow != DirectionArrow.NONE) drawArrow(arrow, size)
        }
    }
}

private val LABEL_STYLE = TextStyle(fontSize = 9.sp, color = Color.Black)
private const val CHIP_PAD_X = 5f
private const val CHIP_PAD_Y = 3f

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawDetectionLabel(
    measurer: TextMeasurer,
    text: String,
    box: PreviewTransform.Rect2,
    chipColor: Color,
    canvas: Size,
) {
    val maxChipWidth = canvas.width.coerceAtLeast(1f)
    val layout = measurer.measure(
        text = text,
        style = LABEL_STYLE,
        overflow = TextOverflow.Ellipsis,
        maxLines = 1,
        constraints = androidx.compose.ui.unit.Constraints(
            maxWidth = (maxChipWidth - 2f * CHIP_PAD_X).toInt().coerceAtLeast(1),
        ),
    )
    val chipW = layout.size.width + 2f * CHIP_PAD_X
    val chipH = layout.size.height + 2f * CHIP_PAD_Y
    // Anchor to the box top-left; sit the chip just above the box, or just
    // inside it when there is no room above, and never let it leave the canvas.
    val left = box.left.coerceIn(0f, (canvas.width - chipW).coerceAtLeast(0f))
    val top = when {
        box.top - chipH >= 0f -> box.top - chipH
        else -> box.top.coerceAtMost((canvas.height - chipH).coerceAtLeast(0f))
    }
    drawRect(color = chipColor, topLeft = Offset(left, top), size = Size(chipW, chipH))
    drawText(layout, topLeft = Offset(left + CHIP_PAD_X, top + CHIP_PAD_Y))
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
