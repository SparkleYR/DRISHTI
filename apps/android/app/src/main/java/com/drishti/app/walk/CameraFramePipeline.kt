package com.drishti.app.walk

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.lifecycle.LifecycleOwner
import com.google.common.util.concurrent.ListenableFuture
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

/**
 * Owns the CameraX use cases for Walk Mode. Bound to the foreground Service's
 * lifecycle so analysis + capture keep running with the screen off; the visible
 * preview surface is attached/detached by the Activity while it is in front.
 */
class CameraFramePipeline(private val context: Context) {

    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private var cameraProvider: ProcessCameraProvider? = null

    private var preview: Preview? = null
    private var analysis: ImageAnalysis? = null
    private var capture: ImageCapture? = null

    /**
     * The visible preview surface, remembered independently of [preview]. The
     * Activity's Compose layer may call [attachPreview] before [start] has built
     * the use case; without this the provider is dropped and the preview stays
     * black (Preview use case reports INACTIVE). We re-apply it as soon as the
     * use case exists.
     */
    @Volatile private var surfaceProvider: Preview.SurfaceProvider? = null

    @Volatile private var frameSink: ((ImageProxy) -> Unit)? = null

    /**
     * @param onFrame receives the latest YUV frame. The callback OWNS the proxy
     * and MUST call [ImageProxy.close] (KEEP_ONLY_LATEST stalls otherwise).
     */
    suspend fun start(owner: LifecycleOwner, targetWidth: Int, onFrame: (ImageProxy) -> Unit) {
        frameSink = onFrame
        val provider = ProcessCameraProvider.getInstance(context).await()
        cameraProvider = provider

        val resolution = ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(
                    Size(targetWidth, targetWidth * 4 / 3),
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER,
                ),
            )
            .build()

        val previewUseCase = Preview.Builder().build()
        val analysisUseCase = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
            .setResolutionSelector(resolution)
            .build()
            .also { it.setAnalyzer(analysisExecutor) { image -> frameSink?.invoke(image) ?: image.close() } }
        val captureUseCase = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .build()

        // bind/unbind + setSurfaceProvider must run on the application main thread.
        withContext(Dispatchers.Main) {
            provider.unbindAll()
            provider.bindToLifecycle(
                owner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                previewUseCase,
                analysisUseCase,
                captureUseCase,
            )
            preview = previewUseCase
            analysis = analysisUseCase
            capture = captureUseCase
            // Apply whatever surface the Activity has already handed us.
            previewUseCase.surfaceProvider = surfaceProvider
        }
    }

    fun attachPreview(provider: Preview.SurfaceProvider) {
        surfaceProvider = provider
        val p = preview ?: return
        androidx.core.content.ContextCompat.getMainExecutor(context).execute {
            p.surfaceProvider = provider
        }
    }

    fun detachPreview() {
        surfaceProvider = null
        val p = preview ?: return
        androidx.core.content.ContextCompat.getMainExecutor(context).execute {
            p.surfaceProvider = null
        }
    }

    fun stop() {
        frameSink = null
        val provider = cameraProvider
        androidx.core.content.ContextCompat.getMainExecutor(context).execute {
            runCatching { provider?.unbindAll() }
        }
        preview = null
        analysis = null
        capture = null
    }

    fun shutdown() {
        stop()
        analysisExecutor.shutdown()
    }

    /** One high-resolution still as an upright JPEG, for OCR / hazard evidence. */
    suspend fun captureStill(maxWidth: Int, quality: Int = 80): ByteArray? {
        val imageCapture = capture ?: return null
        return suspendCancellableCoroutine { cont ->
            imageCapture.takePicture(
                analysisExecutor,
                object : ImageCapture.OnImageCapturedCallback() {
                    override fun onCaptureSuccess(image: ImageProxy) {
                        val bytes = runCatching { image.toUprightJpeg(maxWidth, quality) }.getOrNull()
                        image.close()
                        if (cont.isActive) cont.resume(bytes)
                    }

                    override fun onError(exception: ImageCaptureException) {
                        if (cont.isActive) cont.resume(null)
                    }
                },
            )
        }
    }

    private fun ImageProxy.toUprightJpeg(maxWidth: Int, quality: Int): ByteArray? {
        val raw = planes[0].buffer.let { buf -> ByteArray(buf.remaining()).also { buf.get(it) } }
        var bmp = BitmapFactory.decodeByteArray(raw, 0, raw.size) ?: return null
        val rotation = imageInfo.rotationDegrees
        val longest = maxOf(bmp.width, bmp.height)
        val scale = if (longest > maxWidth) maxWidth.toFloat() / longest else 1f
        if (rotation != 0 || scale != 1f) {
            val m = Matrix()
            if (scale != 1f) m.postScale(scale, scale)
            if (rotation != 0) m.postRotate(rotation.toFloat())
            val next = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
            if (next != bmp) bmp.recycle()
            bmp = next
        }
        return ByteArrayOutputStream().use { out ->
            bmp.compress(Bitmap.CompressFormat.JPEG, quality, out)
            bmp.recycle()
            out.toByteArray()
        }
    }
}

private suspend fun <T> ListenableFuture<T>.await(): T =
    suspendCancellableCoroutine { cont ->
        val direct = Executor { it.run() }
        addListener({
            try {
                cont.resume(get())
            } catch (t: Throwable) {
                cont.cancel(t)
            }
        }, direct)
    }
