package com.drishti.app.hazard

import com.drishti.app.R
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.net.ApiResult
import com.drishti.app.net.CreateHazardRequest
import com.drishti.app.net.Direction
import com.drishti.app.net.DrishtiApi
import com.drishti.app.net.DrishtiJson
import com.drishti.app.net.HazardSeverity
import com.drishti.app.net.VersionedMapCoordinate
import com.drishti.app.net.apiCall
import com.drishti.app.settings.DrishtiSettings
import com.drishti.app.walk.CameraFramePipeline
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant

/**
 * User-confirmed anonymous hazard report. Evidence is attached ONLY when the user
 * gave the extra long-press consent gesture; the request carries no identity.
 */
class HazardReporter(
    private val api: DrishtiApi,
    private val pipeline: CameraFramePipeline,
    private val speech: SpeechEngine,
    private val strings: GuidanceStrings,
) {
    private val jsonType = "application/json".toMediaType()
    private val jpegType = "image/jpeg".toMediaType()

    suspend fun report(
        settings: DrishtiSettings,
        sessionId: String?,
        category: String = "obstacle",
        severity: HazardSeverity = HazardSeverity.MEDIUM,
        direction: Direction? = null,
        withEvidence: Boolean,
    ) {
        val payload = CreateHazardRequest(
            sessionId = sessionId,
            category = category,
            severity = severity,
            confidence = 0.8,
            direction = direction,
            observedAt = Instant.now().toString(),
            mapCoordinate = VersionedMapCoordinate(
                mapId = settings.hazardMapId,
                mapVersion = settings.hazardMapVersion,
                x = settings.hazardMapX.toDouble(),
                y = settings.hazardMapY.toDouble(),
            ),
            temporary = true,
            evidenceConsent = withEvidence,
        )

        val result = if (withEvidence) {
            val jpeg = pipeline.captureStill(maxWidth = 1280)
            if (jpeg == null) {
                submitJson(payload.copy(evidenceConsent = false))
            } else {
                val payloadPart = DrishtiJson.encodeToString(payload).toRequestBody(jsonType)
                val evidencePart = MultipartBody.Part.createFormData(
                    "evidence", "evidence.jpg", jpeg.toRequestBody(jpegType),
                )
                apiCall { api.createHazardWithEvidence(payloadPart, evidencePart) }
            }
        } else {
            submitJson(payload)
        }

        when (result) {
            is ApiResult.Ok -> speech.say(strings.string(R.string.hazard_sent), flush = true)
            else -> speech.say(strings.string(R.string.hazard_failed), flush = true)
        }
    }

    private suspend fun submitJson(payload: CreateHazardRequest) =
        apiCall { api.createHazard(payload) }
}
