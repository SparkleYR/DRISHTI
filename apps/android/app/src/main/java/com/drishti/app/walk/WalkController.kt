package com.drishti.app.walk

import android.content.Context
import android.util.Log
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.lifecycle.LifecycleOwner
import com.drishti.app.R
import com.drishti.app.explore.ExploreController
import com.drishti.app.feedback.AudioFocusManager
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.GyroSteering
import com.drishti.app.feedback.HapticEngine
import com.drishti.app.feedback.SpatialAudioEngine
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.feedback.VoicePrompt
import com.drishti.app.hazard.HazardReporter
import com.drishti.app.hazard.NearbyAdvisor
import com.drishti.app.net.ApiResult
import com.drishti.app.net.DrishtiApi
import com.drishti.app.net.RiskLevel
import com.drishti.app.net.StartWalkSessionRequest
import com.drishti.app.net.WalkSettings
import com.drishti.app.net.apiCall
import com.drishti.app.scene.SceneDescriber
import com.drishti.app.settings.DrishtiSettings
import com.drishti.app.settings.SettingsStore
import com.drishti.app.sos.SosController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant
import java.util.concurrent.atomic.AtomicInteger

/**
 * Orchestrates Walk Mode: session lifecycle, the latest-frame-wins capture loop,
 * response freshness, and fan-out to speech / haptics / spatial audio / overlay.
 * Lives in [WalkForegroundService]; the Activity observes [state].
 */
class WalkController(
    context: Context,
    private val api: DrishtiApi,
    private val settingsStore: SettingsStore,
    private val speech: SpeechEngine,
    private val haptic: HapticEngine,
    private val strings: GuidanceStrings,
) {
    private val app = context.applicationContext
    private val scope = CoroutineScope(Dispatchers.Default + Job())

    private val pipeline = CameraFramePipeline(app)
    private val spatial = SpatialAudioEngine()
    private val gyro = GyroSteering(app)
    private val focus = AudioFocusManager(app)
    private val explore = ExploreController(api, pipeline, speech, strings)
    private val scene = SceneDescriber(api, pipeline, speech, strings, VoicePrompt(app))
    private val hazards = HazardReporter(api, pipeline, speech, strings)
    private val nearby = NearbyAdvisor(api, speech, strings)
    private val sos = SosController(scope, speech, strings)

    private val gate = CaptureLoopGate()
    private val freshness = FrameFreshnessGate()
    private val frameCounter = AtomicInteger(0)
    private val startStopLock = Mutex()

    private val jpegType = "image/jpeg".toMediaType()
    private val textType = "text/plain".toMediaType()

    private var settings: DrishtiSettings = DrishtiSettings()
    private var sessionId: String? = null
    private var maxImageWidth = 1280
    private var maxImageBytes = 5L * 1024 * 1024
    private var maxResultAgeMs = 3000L
    private var recommendedFps = 2.0
    private var nextAllowedAtMs = 0L
    private var announcedSurfaceDegraded = false

    private var tickers = mutableListOf<Job>()
    private var boundOwner: LifecycleOwner? = null
    private var retryJob: Job? = null

    private val _state = MutableStateFlow(WalkUiState(mode = WalkMode.STOPPED))
    val state: StateFlow<WalkUiState> = _state.asStateFlow()

    // ---- lifecycle ---------------------------------------------------------

    fun start(owner: LifecycleOwner) = scope.launch {
        boundOwner = owner
        retryJob?.cancel()
        startStopLock.withLock {
            if (_state.value.mode == WalkMode.WALKING || _state.value.mode == WalkMode.STARTING) return@withLock
            _state.value = WalkUiState(mode = WalkMode.STARTING)
            settings = runCatching { settingsStore.settings.first() }.getOrDefault(DrishtiSettings())
            configureFeedback(settings)
            speech.ensureAudible()

            val started = apiCall {
                api.startSession(
                    StartWalkSessionRequest(
                        deviceAlias = "drishti-android",
                        settings = WalkSettings(
                            speechRate = settings.speechRate.toDouble(),
                            preferredLanguage = settings.language.tag,
                            hapticsEnabled = settings.hapticsEnabled,
                            riskSensitivity = settings.riskSensitivity.toDouble(),
                        ),
                    ),
                )
            }
            when (started) {
                is ApiResult.Ok -> {
                    sessionId = started.value.sessionId
                    maxImageWidth = started.value.maxImageWidth
                    maxImageBytes = started.value.maxImageBytes
                    maxResultAgeMs = started.value.maxResultAgeMs
                    recommendedFps = started.value.recommendedCaptureFps
                }
                is ApiResult.Failure -> return@withLock fail(strings.string(R.string.models_not_ready))
                is ApiResult.Transport -> return@withLock fail(strings.string(R.string.backend_unreachable))
            }

            freshness.reset()
            gate.reset()
            nearby.reset()
            frameCounter.set(0)
            announcedSurfaceDegraded = false
            nextAllowedAtMs = 0L

            spatial.start()
            spatial.setEnabled(settings.spatialAudioEnabled)
            gyro.start()
            focus.acquire()

            runCatching {
                pipeline.start(owner, targetWidth = maxImageWidth, onFrame = ::onCameraFrame)
            }.onFailure {
                Log.e(TAG, "camera start failed", it)
                return@withLock fail("Camera unavailable")
            }

            _state.value = _state.value.copy(mode = WalkMode.WALKING, message = null)
            speech.say(strings.string(R.string.walk_started), flush = true)
            startTickers()
        }
    }

    fun stop() = scope.launch {
        startStopLock.withLock {
            retryJob?.cancel()
            retryJob = null
            boundOwner = null
            tickers.forEach { it.cancel() }
            tickers.clear()
            sos.cancel()
            pipeline.stop()
            spatial.stop()
            gyro.stop()
            focus.release()
            haptic.cancel()
            val id = sessionId
            sessionId = null
            _state.value = WalkUiState(mode = WalkMode.STOPPED)
            speech.say(strings.string(R.string.walk_stopped), flush = true)
            if (id != null) apiCall { api.endSession(id) }
        }
    }

    fun shutdown() {
        // Shared speech/haptic are owned by AppContainer; only tear down what we own.
        scope.launch { stop().join() }
        pipeline.shutdown()
    }

    private fun fail(message: String) {
        _state.value = _state.value.copy(mode = WalkMode.ERROR, message = message)
        speech.say(message, flush = true)
        scope.launch { spatial.stop(); gyro.stop(); focus.release() }
        retryJob?.cancel()
        retryJob = scope.launch {
            delay(4_000)
            val owner = boundOwner
            if (owner != null && _state.value.mode == WalkMode.ERROR) start(owner)
        }
    }

    private fun configureFeedback(s: DrishtiSettings) {
        strings.setLanguage(s.language)
        speech.setLanguage(s.language)
        speech.setRate(s.speechRate)
        haptic.enabled = s.hapticsEnabled
        spatial.setEnabled(s.spatialAudioEnabled)
    }

    private fun startTickers() {
        tickers += scope.launch {
            while (isActive) {
                spatial.applyYaw(gyro.yawDeltaSinceReference(maxResultAgeMs))
                delay(60)
            }
        }
        tickers += scope.launch {
            while (isActive) {
                delay(20_000)
                if (_state.value.mode == WalkMode.WALKING) nearby.poll(settings)
            }
        }
    }

    // ---- capture loop -----------------------------------------------------

    private fun onCameraFrame(image: ImageProxy) {
        val mode = _state.value.mode
        if (mode != WalkMode.WALKING) { image.close(); return }
        val now = System.currentTimeMillis()
        if (now < nextAllowedAtMs || !gate.tryBegin()) { image.close(); return }

        val encoded = runCatching {
            FrameEncoder.encode(image, targetMaxWidth = maxImageWidth, maxBytes = maxImageBytes)
        }.getOrNull()
        image.close()
        if (encoded == null) { gate.finishRequestFailure(); return }

        val frameId = frameCounter.incrementAndGet()
        val capturedAt = Instant.now()
        scope.launch { analyze(encoded.jpeg, frameId, capturedAt) }
    }

    private suspend fun analyze(jpeg: ByteArray, frameId: Int, capturedAt: Instant) {
        val id = sessionId ?: run { gate.finishRequestFailure(); return }
        val framePart = MultipartBody.Part.createFormData("frame", "frame-$frameId.jpg", jpeg.toRequestBody(jpegType))
        val result = apiCall {
            api.analyze(
                frame = framePart,
                sessionId = id.toRequestBody(textType),
                frameId = frameId.toString().toRequestBody(textType),
                capturedAt = capturedAt.toString().toRequestBody(textType),
                rotationDegrees = "0".toRequestBody(textType),
            )
        }
        when (result) {
            is ApiResult.Ok -> {
                if (gate.finishSuccess()) {
                    _state.value = _state.value.copy(connectionLost = false)
                    if (_state.value.mode == WalkMode.WALKING) {
                        speech.say(strings.string(R.string.conn_restored), flush = false)
                    }
                }
                pace(result.value.timings.totalMs, result.value.frameAgeMs)
                applyResponse(result.value)
            }
            is ApiResult.Failure -> {
                when (result.code) {
                    "FRAME_SUPERSEDED", "FRAME_TOO_OLD", "FRAME_ID_NOT_MONOTONIC" -> {
                        gate.finishSuccess() // benign; not a connection problem
                        pace(null, null)
                    }
                    "MODEL_NOT_READY", "SESSION_NOT_FOUND", "SESSION_ENDED" -> {
                        gate.finishRequestFailure()
                        _state.value = _state.value.copy(message = strings.string(R.string.models_not_ready))
                        pace(null, null)
                    }
                    else -> { gate.finishRequestFailure(); pace(null, null) }
                }
            }
            is ApiResult.Transport -> {
                if (gate.finishConnectionFailure()) {
                    _state.value = _state.value.copy(connectionLost = true)
                    speech.say(strings.string(R.string.conn_lost), flush = true)
                }
                pace(null, null)
            }
        }
    }

    private fun pace(totalMs: Double?, frameAgeMs: Double?) {
        val delayMs = CapturePacing.nextDelayMs(
            CapturePacing.Input(
                consecutiveFailures = gate.consecutiveFailures,
                frameAgeMs = frameAgeMs,
                maxResultAgeMs = maxResultAgeMs,
                recommendedFps = recommendedFps,
                totalProcessingMs = totalMs,
            ),
        )
        nextAllowedAtMs = System.currentTimeMillis() + delayMs
    }

    private fun applyResponse(resp: com.drishti.app.net.FrameAnalysisResponse) {
        // A response from a request that was in flight when the user switched to
        // Explore / Scene / SOS must not speak or vibrate over that mode.
        if (_state.value.mode != WalkMode.WALKING) return
        val verdict = freshness.evaluate(
            FrameFreshnessGate.Input(
                responseSessionId = resp.sessionId,
                activeSessionId = sessionId,
                sessionRunning = _state.value.mode == WalkMode.WALKING,
                frameId = resp.frameId,
                overlayValidUntil = parseInstant(resp.overlay.validUntil),
                capturedAt = parseInstant(resp.capturedAt),
                maxResultAgeMs = maxResultAgeMs,
            ),
        )
        if (verdict is FrameFreshnessGate.Verdict.Discard) {
            Log.d(TAG, "discard frame ${resp.frameId}: ${verdict.reason}")
            return
        }
        freshness.markApplied(resp.frameId)
        gyro.markReference()

        val degraded = resp.degradedModules.any { it == "segmentation" || it == "india_hazards" }
        _state.value = _state.value.copy(
            guidance = resp.guidance,
            detections = resp.detections,
            overlay = resp.overlay,
            geometry = resp.geometry,
            surfacesDegraded = degraded,
            lastTotalMs = resp.timings.totalMs,
            reason = strings.reasonText(resp.guidance),
            message = null,
        )

        val phrase = strings.speechFor(resp.guidance)
        if (resp.guidance.speak && phrase != null) {
            val flush = resp.guidance.level == RiskLevel.HIGH ||
                resp.guidance.level == RiskLevel.CRITICAL ||
                resp.guidance.action == com.drishti.app.net.GuidanceAction.STOP
            speech.say(phrase, flush = flush)
        }
        haptic.play(resp.guidance.hapticPattern, resp.guidance.action)
        spatial.updateFromDetections(resp.detections)

        if (degraded && !announcedSurfaceDegraded) {
            announcedSurfaceDegraded = true
            speech.say(strings.string(R.string.surface_degraded), flush = false)
        }
    }

    // ---- user actions ---------------------------------------------------

    fun repeatLast() {
        if (!speech.repeatLast()) speech.say(strings.string(R.string.repeat_hint), flush = true)
    }

    private var exploreClearJob: Job? = null

    fun triggerExplore() = scope.launch {
        if (_state.value.mode != WalkMode.WALKING) return@launch
        _state.value = _state.value.copy(mode = WalkMode.READING)
        spatial.clear()
        haptic.ack()
        val result = explore.readTextOnce()
        if (result != null) {
            _state.value = _state.value.copy(
                explore = ExploreCard(
                    text = result.text,
                    routeNumbers = result.routeNumbers,
                    quality = result.confidenceQualification,
                    shownAtMs = System.currentTimeMillis(),
                ),
            )
            exploreClearJob?.cancel()
            exploreClearJob = scope.launch {
                delay(20_000)
                _state.value = _state.value.copy(explore = null)
            }
        }
        if (_state.value.mode == WalkMode.READING) {
            _state.value = _state.value.copy(mode = WalkMode.WALKING)
        }
    }

    private var sceneClearJob: Job? = null

    /**
     * On-demand VLM scene description. Pauses the Walk loop, captures a voice
     * question, round-trips the slow `/vlm/query` endpoint, speaks the answer,
     * then resumes. Deliberately separate from the real-time loop.
     */
    fun triggerDescribe() = scope.launch {
        if (_state.value.mode != WalkMode.WALKING) return@launch
        _state.value = _state.value.copy(mode = WalkMode.DESCRIBING, message = null)
        spatial.clear()
        haptic.ack()
        val result = scene.describeOnce(settings.language.tag)
        if (result != null) {
            _state.value = _state.value.copy(
                scene = SceneCard(
                    question = result.question,
                    answer = result.answer,
                    totalMs = result.totalMs,
                    shownAtMs = System.currentTimeMillis(),
                ),
            )
            sceneClearJob?.cancel()
            sceneClearJob = scope.launch {
                delay(35_000)
                _state.value = _state.value.copy(scene = null)
            }
        }
        if (_state.value.mode == WalkMode.DESCRIBING) {
            _state.value = _state.value.copy(mode = WalkMode.WALKING)
        }
    }

    fun armHazard() {
        if (_state.value.mode != WalkMode.WALKING) return
        haptic.ack()
        _state.value = _state.value.copy(hazardArming = true, message = strings.string(R.string.hazard_prompt))
        speech.say(strings.string(R.string.hazard_prompt), flush = true)
        scope.launch {
            delay(8_000)
            if (_state.value.hazardArming) {
                _state.value = _state.value.copy(hazardArming = false, message = null)
            }
        }
    }

    fun confirmHazard(withEvidence: Boolean) = scope.launch {
        if (!_state.value.hazardArming) return@launch
        _state.value = _state.value.copy(hazardArming = false, message = null)
        val dir = _state.value.detections.maxByOrNull { it.riskScore }?.direction
        hazards.report(settings, sessionId, direction = dir, withEvidence = withEvidence)
    }

    fun cancelHazard() {
        if (!_state.value.hazardArming) return
        _state.value = _state.value.copy(hazardArming = false, message = null)
        speech.say(strings.string(R.string.hazard_cancelled), flush = true)
    }

    fun toggleBlank() {
        val blank = !_state.value.screenBlank
        _state.value = _state.value.copy(screenBlank = blank)
        speech.say(
            strings.string(if (blank) R.string.screen_blanked else R.string.screen_unblanked),
            flush = true,
        )
    }

    fun triggerSos() {
        haptic.play(com.drishti.app.net.HapticPattern.CRITICAL_RAPID)
        _state.value = _state.value.copy(mode = WalkMode.SOS)
        sos.activate()
    }

    fun cancelSos() {
        if (_state.value.mode != WalkMode.SOS) return
        sos.cancel()
        _state.value = _state.value.copy(mode = if (sessionId != null) WalkMode.WALKING else WalkMode.STOPPED)
    }

    // ---- preview surface (Activity attaches/detaches) --------------------

    fun attachPreview(surfaceProvider: Preview.SurfaceProvider) = pipeline.attachPreview(surfaceProvider)
    fun detachPreview() = pipeline.detachPreview()

    private fun parseInstant(value: String): Instant =
        runCatching { Instant.parse(value) }.getOrElse { Instant.now().plusSeconds(1) }

    private companion object { const val TAG = "WalkController" }
}
