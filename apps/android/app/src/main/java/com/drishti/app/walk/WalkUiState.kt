package com.drishti.app.walk

import com.drishti.app.net.DetectionResult
import com.drishti.app.net.FrameGeometry
import com.drishti.app.net.GuidanceContract
import com.drishti.app.net.OcrConfidenceQualification
import com.drishti.app.net.OverlayContract
import com.drishti.app.net.TargetTrackingTelemetry

enum class WalkMode { STARTING, WALKING, PAUSED, READING, DESCRIBING, SOS, STOPPED, ERROR }

/** Last on-demand OCR read, surfaced on screen (not only spoken). */
data class ExploreCard(
    val text: String,
    val routeNumbers: List<String>,
    val quality: OcrConfidenceQualification,
    val shownAtMs: Long,
)

/** Last on-demand VLM scene answer, surfaced on screen (not only spoken). */
data class SceneCard(
    val question: String,
    val answer: String,
    val totalMs: Double,
    val shownAtMs: Long,
)

/** Everything the Walk UI renders. Emitted as a StateFlow by [WalkController]. */
data class WalkUiState(
    val mode: WalkMode = WalkMode.STARTING,
    val guidance: GuidanceContract? = null,
    val detections: List<DetectionResult> = emptyList(),
    val overlay: OverlayContract? = null,
    val geometry: FrameGeometry? = null,
    val surfacesDegraded: Boolean = false,
    val connectionLost: Boolean = false,
    val lastTotalMs: Double? = null,
    val hazardArming: Boolean = false,
    val screenBlank: Boolean = false,
    val message: String? = null,
    /** Human-readable "why" for the current guidance, e.g. why it says STOP. */
    val reason: String? = null,
    /** Last OCR read to display on screen; null once dismissed / timed out. */
    val explore: ExploreCard? = null,
    /** Last VLM scene answer to display on screen; null once dismissed / timed out. */
    val scene: SceneCard? = null,
    /** Latest Ask -> Guide target telemetry from the backend; null until first frame. */
    val target: TargetTrackingTelemetry? = null,
)
