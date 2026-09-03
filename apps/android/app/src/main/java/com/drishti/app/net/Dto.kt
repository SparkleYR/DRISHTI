@file:OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)

package com.drishti.app.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy

/**
 * Wire models mirroring packages/contracts/src/index.ts (contract version 1.0.0).
 * Kotlin properties stay camelCase; [DrishtiJson] maps them to snake_case on the wire.
 * Enum constants already match the wire spelling (UPPER_SNAKE) so need no aliases.
 */
val DrishtiJson: Json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    namingStrategy = JsonNamingStrategy.SnakeCase
    coerceInputValues = true
}

// ---- Enums -----------------------------------------------------------------

enum class ServiceStatus { OK, DEGRADED, UNAVAILABLE }
enum class ModuleStatus { READY, DEGRADED, UNAVAILABLE, LOADING }
enum class ComputeDevice { CUDA, CPU, NONE }

enum class Direction { LEFT, CENTRE, RIGHT, UNKNOWN }
enum class CorridorChoice { LEFT, CENTRE, RIGHT, NONE }
enum class ProximityBand { FAR, MEDIUM, NEAR, IMMEDIATE, UNKNOWN }
enum class ApproachState { APPROACHING, RECEDING, STATIONARY, UNKNOWN }
enum class RiskLevel { CLEAR, WATCH, WARN, HIGH, CRITICAL }
enum class DisplayColor { GREEN, YELLOW, RED, GREY }
enum class GuidanceAction { CLEAR, CAUTION, MOVE_LEFT, MOVE_RIGHT, STOP, PAUSE_UNCLEAR }
enum class HapticPattern { NONE, CAUTION_SHORT, WARNING_DOUBLE, CRITICAL_RAPID, UNCLEAR_LONG }
enum class DirectionArrow { LEFT, RIGHT, STOP, NONE }
enum class SurfaceKind { WALKABLE, ROAD, NON_WALKABLE, UNKNOWN }

enum class HazardSeverity { LOW, MEDIUM, HIGH, CRITICAL }
enum class HazardStatus { NEW, VERIFIED, ASSIGNED, IN_PROGRESS, RESOLVED, REJECTED }
enum class OcrConfidenceQualification { HIGH, LOW, NONE }

enum class TargetTrackingState { IDLE, LOCATING, LOCKED_TRACKING, TARGET_LOST }
enum class TargetHapticPattern { NONE, TARGET_LEFT_PULSE, TARGET_CENTRE_PULSE, TARGET_RIGHT_PULSE }

// ---- Common geometry -----------------------------------------------------------

@Serializable
data class NormalizedPoint(val x: Double, val y: Double)

@Serializable
data class NormalizedBoundingBox(val x1: Double, val y1: Double, val x2: Double, val y2: Double)

@Serializable
data class MotionVector(val dx: Double, val dy: Double)

// ---- Error envelope ----------------------------------------------------------

@Serializable
data class ApiErrorBody(
    val code: String,
    val message: String,
    val retryable: Boolean = false,
)

@Serializable
data class ApiErrorResponse(
    val schemaVersion: String? = null,
    val serverTime: String? = null,
    val error: ApiErrorBody,
)

// ---- Health ----------------------------------------------------------------

@Serializable
data class ModuleHealth(val status: ModuleStatus, val detail: String? = null)

@Serializable
data class HealthService(val name: String, val version: String)

@Serializable
data class HealthCompute(val selectedDevice: ComputeDevice, val deviceName: String? = null)

@Serializable
data class HealthModels(
    val detector: ModuleHealth,
    val segmentation: ModuleHealth,
    val tracker: ModuleHealth,
    val depth: ModuleHealth,
    val indiaHazards: ModuleHealth,
    val ocr: ModuleHealth,
    val vlm: ModuleHealth,
)

@Serializable
data class HealthResponse(
    val schemaVersion: String,
    val serverTime: String,
    val status: ServiceStatus,
    val runtimeMode: String,
    val service: HealthService,
    val compute: HealthCompute,
    val models: HealthModels,
    val database: ModuleHealth,
    val walkModeAvailable: Boolean,
)

// ---- Walk sessions -------------------------------------------------------------

@Serializable
data class WalkSettings(
    val speechRate: Double? = null,
    val preferredLanguage: String? = null,
    val hapticsEnabled: Boolean? = null,
    val riskSensitivity: Double? = null,
)

@Serializable
data class StartWalkSessionRequest(
    val deviceAlias: String? = null,
    val settings: WalkSettings? = null,
)

@Serializable
data class StartWalkSessionResponse(
    val schemaVersion: String,
    val serverTime: String,
    val sessionId: String,
    val startedAt: String,
    val recommendedCaptureFps: Double,
    val maxImageWidth: Int,
    val maxImageBytes: Long,
    val maxResultAgeMs: Long,
)

@Serializable
data class EndWalkSessionResponse(
    val schemaVersion: String,
    val serverTime: String,
    val sessionId: String,
    val endedAt: String,
    val status: String,
)

// ---- Frame analysis -------------------------------------------------------------

@Serializable
data class FrameGeometry(
    val coordinateSpace: String,
    val sourceWidth: Int,
    val sourceHeight: Int,
    val rotationDegrees: Int,
    val mirrored: Boolean = false,
)

@Serializable
data class DetectionResult(
    val trackId: Int? = null,
    val label: String,
    val confidence: Double,
    val bbox: NormalizedBoundingBox,
    val anchor: NormalizedPoint,
    val direction: Direction,
    val proximity: ProximityBand,
    val proximityScore: Double? = null,
    val approachState: ApproachState,
    val approachRate: Double? = null,
    val motionVector: MotionVector? = null,
    val pathOverlap: Double,
    val riskScore: Double,
    val riskLevel: RiskLevel,
    val displayColor: DisplayColor,
)

@Serializable
data class SurfaceRegion(
    val kind: SurfaceKind,
    val confidence: Double,
    val polygon: List<NormalizedPoint>,
    val sourceFrameId: Int,
)

@Serializable
data class CorridorCosts(
    val leftCost: Double,
    val centreCost: Double,
    val rightCost: Double,
)

@Serializable
data class OverlayContract(
    val coordinateSpace: String,
    val preferredCorridor: CorridorChoice,
    val safePolygons: List<List<NormalizedPoint>> = emptyList(),
    val blockedPolygons: List<List<NormalizedPoint>> = emptyList(),
    val uncertainPolygons: List<List<NormalizedPoint>> = emptyList(),
    val directionArrow: DirectionArrow,
    val validUntil: String,
)

@Serializable
data class GuidanceContract(
    val level: RiskLevel,
    val action: GuidanceAction,
    val speech: String,
    val hapticPattern: HapticPattern,
    val speak: Boolean,
    val reasonCode: String,
)

@Serializable
data class StageTimings(
    val decodeMs: Double = 0.0,
    val detectionMs: Double? = null,
    val segmentationMs: Double? = null,
    val trackingDepthMs: Double? = null,
    val spatialMs: Double? = null,
    val riskMs: Double? = null,
    val totalMs: Double,
)

@Serializable
data class FrameAnalysisResponse(
    val schemaVersion: String,
    val serverTime: String,
    val sessionId: String,
    val frameId: Int,
    val capturedAt: String,
    val receivedAt: String,
    val processedAt: String,
    val frameAgeMs: Double,
    val geometry: FrameGeometry,
    val detections: List<DetectionResult> = emptyList(),
    val surfaces: List<SurfaceRegion> = emptyList(),
    val corridors: CorridorCosts,
    val overlay: OverlayContract,
    val guidance: GuidanceContract,
    val targetTracking: TargetTrackingTelemetry? = null,
    val timings: StageTimings,
    val degradedModules: List<String> = emptyList(),
)

// ---- Explore --------------------------------------------------------------------

@Serializable
data class ExploreTimings(val decodeMs: Double, val ocrMs: Double, val totalMs: Double)

@Serializable
data class ReadTextResponse(
    val schemaVersion: String,
    val serverTime: String,
    val mode: String,
    val language: String,
    val text: String,
    val routeNumbers: List<String> = emptyList(),
    val confidence: Double,
    val confidenceQualification: OcrConfidenceQualification,
    val message: String,
    val noTextFound: Boolean,
    val timings: ExploreTimings,
)

// ---- Target tracking telemetry (Ask -> Lock -> Guide) -----------------------

/**
 * Per-frame assistive target metadata on every [FrameAnalysisResponse].
 * The backend is the authority: [speak]/[hapticPattern] are what the client
 * should render, and when [isSafetyOverridden] is true they are already
 * blanked so safety guidance stays the only immediate instruction.
 */
@Serializable
data class TargetTrackingTelemetry(
    val trackingState: TargetTrackingState = TargetTrackingState.IDLE,
    val targetName: String? = null,
    val clockDirection: String? = null,
    val targetCenter: NormalizedPoint? = null,
    val confidence: Double? = null,
    val isSafetyOverridden: Boolean = false,
    val speech: String = "",
    val speak: Boolean = false,
    val hapticPattern: TargetHapticPattern = TargetHapticPattern.NONE,
)

// ---- VLM locate (Ask -> Lock) ---------------------------------------------

@Serializable
data class VlmTargetBox(
    val xMin: Double,
    val yMin: Double,
    val xMax: Double,
    val yMax: Double,
)

@Serializable
data class VlmLocatedTarget(
    val label: String,
    val confidence: Double? = null,
    val box: VlmTargetBox,
    val point: NormalizedPoint,
)

@Serializable
data class VlmLocateResponse(
    val schemaVersion: String,
    val serverTime: String,
    val model: String,
    val text: String,
    val target: VlmLocatedTarget,
    val clockDirection: String,
    val trackingAllowed: Boolean,
    val sourceFrameId: Int? = null,
    val timings: VlmTimings,
)

// ---- VLM (on-demand scene description / Q&A) ---------------------------------

@Serializable
data class VlmTimings(
    val decodeMs: Double,
    val loadMs: Double,
    val inferenceMs: Double,
    val unloadMs: Double,
    val totalMs: Double,
)

@Serializable
data class VlmQueryResponse(
    val schemaVersion: String,
    val serverTime: String,
    val model: String,
    val text: String,
    val timings: VlmTimings,
)

// ---- Hazards ------------------------------------------------------------------

@Serializable
data class VersionedMapCoordinate(
    val mapId: String,
    val mapVersion: String,
    val x: Double,
    val y: Double,
)

@Serializable
data class CreateHazardRequest(
    val sessionId: String? = null,
    val category: String,
    val severity: HazardSeverity,
    val confidence: Double,
    val riskScore: Double? = null,
    val direction: Direction? = null,
    val observedAt: String,
    val mapCoordinate: VersionedMapCoordinate? = null,
    val temporary: Boolean,
    val evidenceConsent: Boolean,
)

@Serializable
data class HazardRecord(
    val id: String,
    val category: String,
    val severity: HazardSeverity,
    val status: HazardStatus,
    val mapCoordinate: VersionedMapCoordinate? = null,
    val firstSeenAt: String,
    val lastSeenAt: String,
    val confidence: Double,
    val confirmationCount: Int,
    val temporary: Boolean,
    val version: Int,
    val hasConsentedEvidence: Boolean,
)

@Serializable
data class HazardResponse(
    val schemaVersion: String,
    val serverTime: String,
    val hazard: HazardRecord,
    val mergedWithExisting: Boolean,
)

@Serializable
data class HazardListResponse(
    val schemaVersion: String,
    val serverTime: String,
    val items: List<HazardRecord> = emptyList(),
    val nextCursor: String? = null,
)
