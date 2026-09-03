package com.drishti.app.ui.gestures

import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalViewConfiguration
import kotlin.math.abs

/**
 * Zero-look gesture set (ANDROID_APP_SPEC §6). One-finger taps/long-press go
 * through [detectTapGestures]; multi-finger and directional swipes use a small
 * hand-rolled recogniser so the whole screen is one target.
 */
fun Modifier.walkGestures(
    onDoubleTap: () -> Unit,
    onSingleTap: () -> Unit,
    onLongPress: () -> Unit,
    onTripleTap: () -> Unit,
    onTwoFingerTap: () -> Unit,
    onThreeFingerTap: () -> Unit,
    onTwoFingerSwipeUp: () -> Unit,
    onTwoFingerSwipeRight: () -> Unit,
): Modifier = composed {
    val vc = LocalViewConfiguration.current
    val touchSlop = vc.touchSlop

    this
        .pointerInput(Unit) {
            var tapWindowStart = 0L
            var tapCount = 0
            detectTapGestures(
                onLongPress = { onLongPress() },
                onDoubleTap = { onDoubleTap() },
                onTap = {
                    val now = System.currentTimeMillis()
                    if (now - tapWindowStart > 500) { tapWindowStart = now; tapCount = 1 } else tapCount++
                    when (tapCount) {
                        1 -> onSingleTap()
                        3 -> { onTripleTap(); tapCount = 0 }
                    }
                },
            )
        }
        .pointerInput(Unit) {
            awaitEachGesture {
                val first = awaitFirstDown(requireUnconsumed = false)
                var maxPointers = 1
                val startCentroid = first.position
                var lastCentroid = first.position
                var moved = false
                while (true) {
                    val event = awaitPointerEvent(PointerEventPass.Initial)
                    val active = event.changes.filter { it.pressed }
                    if (active.isEmpty()) break
                    maxPointers = maxOf(maxPointers, active.size)
                    val c = active.fold(Offset.Zero) { acc, p -> acc + p.position } / active.size.toFloat()
                    lastCentroid = c
                    if ((c - startCentroid).getDistance() > touchSlop * 2) moved = true
                }
                val dx = lastCentroid.x - startCentroid.x
                val dy = lastCentroid.y - startCentroid.y
                when {
                    maxPointers >= 3 -> onThreeFingerTap()
                    maxPointers == 2 && moved && abs(dy) > abs(dx) && dy < -touchSlop * 6 -> onTwoFingerSwipeUp()
                    maxPointers == 2 && moved && abs(dx) > abs(dy) && dx > touchSlop * 6 -> onTwoFingerSwipeRight()
                    maxPointers == 2 && !moved -> onTwoFingerTap()
                }
            }
        }
}
