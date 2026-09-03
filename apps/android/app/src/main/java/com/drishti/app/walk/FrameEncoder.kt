package com.drishti.app.walk

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Matrix
import android.graphics.Rect
import android.graphics.YuvImage
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream

/**
 * YUV_420_888 → upright, size-bounded JPEG. The app always sends an already
 * orientation-corrected image, so `rotation_degrees = 0` goes on the wire and
 * the backend geometry matches the JPEG 1:1 (ANDROID_APP_SPEC §3.7).
 */
object FrameEncoder {

    data class Encoded(val jpeg: ByteArray, val width: Int, val height: Int)

    fun encode(
        image: ImageProxy,
        targetMaxWidth: Int,
        maxBytes: Long,
        initialQuality: Int = 60,
    ): Encoded? {
        val rotation = image.imageInfo.rotationDegrees
        val nv21 = yuv420ToNv21(image) ?: return null
        val yuv = YuvImage(nv21, ImageFormat.NV21, image.width, image.height, null)

        val firstPass = ByteArrayOutputStream()
        if (!yuv.compressToJpeg(Rect(0, 0, image.width, image.height), 85, firstPass)) return null
        var bitmap = BitmapFactory.decodeByteArray(firstPass.toByteArray(), 0, firstPass.size())
            ?: return null

        // Upright + downscale in one matrix.
        val longestUpright = if (rotation == 90 || rotation == 270) bitmap.height else bitmap.width
        val scale = if (longestUpright > targetMaxWidth) targetMaxWidth.toFloat() / longestUpright else 1f
        if (rotation != 0 || scale != 1f) {
            val m = Matrix()
            if (scale != 1f) m.postScale(scale, scale)
            if (rotation != 0) m.postRotate(rotation.toFloat())
            val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, m, true)
            if (rotated != bitmap) bitmap.recycle()
            bitmap = rotated
        }

        var quality = initialQuality
        var out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
        while (out.size() > maxBytes && quality > 30) {
            quality -= 10
            out = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
        }
        val w = bitmap.width
        val h = bitmap.height
        bitmap.recycle()
        if (out.size() > maxBytes) return null
        return Encoded(out.toByteArray(), w, h)
    }

    private fun yuv420ToNv21(image: ImageProxy): ByteArray? {
        if (image.format != ImageFormat.YUV_420_888) return null
        val width = image.width
        val height = image.height
        val ySize = width * height
        val nv21 = ByteArray(ySize + ySize / 2)

        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]

        // Y
        val yBuffer = yPlane.buffer
        val yRowStride = yPlane.rowStride
        var pos = 0
        if (yRowStride == width) {
            yBuffer.get(nv21, 0, ySize)
            pos = ySize
        } else {
            val row = ByteArray(yRowStride)
            for (r in 0 until height) {
                yBuffer.position(r * yRowStride)
                yBuffer.get(row, 0, width.coerceAtMost(yRowStride))
                System.arraycopy(row, 0, nv21, pos, width)
                pos += width
            }
        }

        // Interleaved VU
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer
        val uRowStride = uPlane.rowStride
        val uPixelStride = uPlane.pixelStride
        val vRowStride = vPlane.rowStride
        val vPixelStride = vPlane.pixelStride
        val chromaHeight = height / 2
        val chromaWidth = width / 2
        for (r in 0 until chromaHeight) {
            for (c in 0 until chromaWidth) {
                val vIndex = r * vRowStride + c * vPixelStride
                val uIndex = r * uRowStride + c * uPixelStride
                nv21[pos++] = vBuffer.get(vIndex)
                nv21[pos++] = uBuffer.get(uIndex)
            }
        }
        return nv21
    }
}
